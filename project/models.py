import torch
import torch.nn as nn
import math
import matplotlib.pyplot as plt
# Ignore warnings
import warnings
warnings.filterwarnings("ignore")

class SinusoidalPositionEmbeddings(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.dim = dim

    def forward(self, time):
        device = time.device
        half_dim = self.dim // 2
        embeddings = math.log(10000) / (half_dim - 1)
        embeddings = torch.exp(torch.arange(half_dim, device=device) * -embeddings)
        embeddings = time[:, None] * embeddings[None, :]
        embeddings = torch.cat((embeddings.sin(), embeddings.cos()), dim=-1)

        return embeddings
    
    def plot(self, T):
        all_t = torch.arange(1, T+1)
        test_embed = SinusoidalPositionEmbeddings(dim=32)
        output = test_embed(all_t)

        plt.figure(figsize=(10,4))
        plt.imshow(output, cmap='viridis', aspect='auto')
        plt.colorbar()
        plt.title('Time embedding Visualization')
        plt.ylabel('Time step')
        plt.show()

class SpatialAttention(nn.Module):
    def __init__(self, kernel_size=7):
        super(SpatialAttention, self).__init__()
        self.conv = nn.Conv2d(2, 1, kernel_size=kernel_size, padding=kernel_size // 2)

    def forward(self, x):
        # Average and Max pooling features
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out = torch.max(x, dim=1, keepdim=True)[0]

        # Concatenate along channel dimension
        concat = torch.cat((avg_out, max_out), dim=1)

        # Apply convolution to create attention map
        attention = torch.sigmoid(self.conv(concat))

        # Multiply attention map with input features
        return x * attention
    
class ChannelAttention(nn.Module):
    def __init__(self, num_channels, reduction_ratio=16):
        super(ChannelAttention, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(num_channels, num_channels // reduction_ratio, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(num_channels // reduction_ratio, num_channels, bias=False),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        b, c, _, _ = x.size()
        y = self.avg_pool(x).view(b, c)
        y = self.fc(y).view(b, c, 1, 1)
        return x * y.expand_as(x)

class Block(nn.Module):
    def __init__(self, in_ch, out_ch, time_emb_dim, attention, up=False, dropout=None):
        super().__init__()

        self.time_mlp =  nn.Linear(time_emb_dim, out_ch)
        if up:
            self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
            self.transform = nn.ConvTranspose2d(out_ch, out_ch, 4, 2, 1)
        else:
            self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
            self.transform = nn.Conv2d(out_ch, out_ch, 4, 2, 1)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.bnorm1 = nn.BatchNorm2d(out_ch)
        self.bnorm2 = nn.BatchNorm2d(out_ch)
        self.relu  = nn.ReLU()
        self.attention = False
        if attention:
            print("Model created with attention")
            self.spatial_attention = SpatialAttention()
            self.attention = True
            
        self.dropout = dropout
        
        if self.dropout:
            self.drop = nn.Dropout(p=self.dropout)

    def forward(self, x, t, ):
        # First Conv
        h = self.bnorm1(self.relu(self.conv1(x)))
        # Time embedding
        time_emb = self.relu(self.time_mlp(t))
        # Extend last 2 dimensions
        time_emb = time_emb[(..., ) + (None, ) * 2]
        # Add time channel
        h = h + time_emb
        # Second Conv
        h = self.bnorm2(self.relu(self.conv2(h)))
        if self.attention:
            h = self.spatial_attention(h)
            
        if self.dropout:
            h = self.drop(h)
            
        # Down or Upsample
        h = self.transform(h)

        return h

class SimpleUnet(nn.Module):
    """
    A simplified variant of the Unet architecture.
    """
    def __init__(self, unet_channels=(64, 128, 256, 512, 1024), input_channels=3,
                  output_channels=3, time_emb_dim=32, attention=False, dropout=None):
        super().__init__()
        self.input_channels = input_channels
        self.output_channels = output_channels
        self.down_channels = unet_channels
        self.up_channels = unet_channels[::-1]
        self.up_in_channels = [self.up_channels[0]] + [self.up_channels[i] * 2 for i in range(1, len(self.up_channels))]
        print("Up in channels: ", self.up_in_channels)

        self.time_emb_dim = time_emb_dim

        # Time embedding
        self.time_mlp = nn.Sequential(
                SinusoidalPositionEmbeddings(self.time_emb_dim),
                nn.Linear(self.time_emb_dim, self.time_emb_dim),
                nn.ReLU()
            )

        # Initial projection
        self.conv0 = nn.Conv2d(self.input_channels, self.down_channels[0], 3, padding=1)

        # Downsample
        self.downs = nn.ModuleList([Block(self.down_channels[i], self.down_channels[i+1], \
                                    self.time_emb_dim, attention, dropout=dropout) \
                    for i in range(len(self.down_channels)-1)])
        # Upsample
        self.ups = nn.ModuleList([Block(self.up_in_channels[i], self.up_channels[i+1], \
                                        self.time_emb_dim, attention, up=True, dropout=dropout) \
                    for i in range(len(self.up_channels)-1)])

        # Edit: Corrected a bug found by Jakub C (see YouTube comment)
        self.output = nn.Conv2d(self.up_channels[-1], self.output_channels, 1)

    def forward(self, x, timestep):
        # Embedd time
        t = self.time_mlp(timestep)
        # Initial conv
        x = self.conv0(x)
        # Unet
        residual_inputs = [x]
        for i, down in enumerate(self.downs):
            x = down(x, t)
            if i < len(self.downs) - 1:
                residual_inputs.append(x)
        for i, up in enumerate(self.ups):
            if i != 0:
                residual_x = residual_inputs.pop()
                # Add residual x as additional channels
                x = torch.cat((x, residual_x), dim=1)
            x = up(x, t)
        x = self.output(x)
        return x