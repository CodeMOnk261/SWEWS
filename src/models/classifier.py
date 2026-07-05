import math
import torch
import torch.nn as nn

class PositionalEncoding(nn.Module):
    """
    Standard sinusoidal positional encoding to inject order information into the
    transformer input sequence.
    """
    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        
        # Apply sine to even indices and cosine to odd indices
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Tensor of shape [batch_size, seq_len, d_model]
        Returns:
            Tensor with positional encodings added.
        """
        return x + self.pe[:, :x.size(1)]

class AttentionPooling(nn.Module):
    """
    Attention-based pooling to aggregate sequence outputs instead of simple mean pooling.
    Computes a query-key attention score for each step in the sequence.
    """
    def __init__(self, d_model: int):
        super().__init__()
        self.attn_weights = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.Tanh(),
            nn.Linear(d_model // 2, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Tensor of shape [batch_size, seq_len, d_model]
        Returns:
            Pooled tensor of shape [batch_size, d_model]
        """
        # Compute weights: [batch_size, seq_len, 1]
        weights = self.attn_weights(x)
        weights = torch.softmax(weights, dim=1)
        
        # Weighted sum: [batch_size, d_model]
        pooled = torch.sum(x * weights, dim=1)
        return pooled

class SpaceWeatherTransformerClassifier(nn.Module):
    """
    Transformer Encoder Classifier for Space Weather Storm Classification.
    Classifies a sequence of features into: Safe (0), Moderate (1), or Severe (2).
    """
    def __init__(self, input_dim: int, d_model: int = 64, nhead: int = 4, 
                 num_layers: int = 3, dim_feedforward: int = 128, 
                 num_classes: int = 3, dropout: float = 0.1):
        super().__init__()
        
        # Project raw features to model dimension
        self.feature_projection = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        
        # Transformer Encoder Block
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, 
            nhead=nhead, 
            dim_feedforward=dim_feedforward, 
            dropout=dropout, 
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Attention pooling layer to condense sequence information
        self.pool = AttentionPooling(d_model)
        
        # Classification Head
        self.classifier_head = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, num_classes)
        )
        
    def forward(self, src: torch.Tensor, src_mask: torch.Tensor = None) -> torch.Tensor:
        """
        Args:
            src: Tensor of shape [batch_size, seq_len, input_dim]
            src_mask: Optional padding mask or attention mask
        Returns:
            logits: Output classification logits of shape [batch_size, num_classes]
        """
        # Project and encode features: [batch_size, seq_len, d_model]
        x = self.feature_projection(src)
        x = self.pos_encoder(x)
        
        # Transformer encoding: [batch_size, seq_len, d_model]
        x_encoded = self.transformer_encoder(x, mask=src_mask)
        
        # Pooling over time steps: [batch_size, d_model]
        pooled_out = self.pool(x_encoded)
        
        # Classification: [batch_size, num_classes]
        logits = self.classifier_head(pooled_out)
        return logits
