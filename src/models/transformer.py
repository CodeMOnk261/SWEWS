import torch
import torch.nn as nn
import torch.nn.functional as F

class GatedLinearUnit(nn.Module):
    """
    Gated Linear Unit (GLU) block to select relevant information.
    """
    def __init__(self, d_model: int):
        super().__init__()
        self.fc = nn.Linear(d_model, d_model * 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: [..., d_model]
        x_proj = self.fc(x)
        val, gate = x_proj.chunk(2, dim=-1)
        return val * torch.sigmoid(gate)

class GatedResidualNetwork(nn.Module):
    """
    Gated Residual Network (GRN) to allow adaptive non-linear processing.
    """
    def __init__(self, d_model: int, dropout: float = 0.1):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model)
        self.fc2 = nn.Linear(d_model, d_model)
        self.glu = GatedLinearUnit(d_model)
        self.layernorm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, context: torch.Tensor = None) -> torch.Tensor:
        # x: [..., d_model]
        h = F.elu(self.fc1(x))
        if context is not None:
            # Inject context if provided
            h = h + context
        h = self.dropout(self.fc2(h))
        # Gating and residual skip connection
        gated = self.glu(h)
        return self.layernorm(x + gated)

class VariableSelectionNetwork(nn.Module):
    """
    Variable Selection Network (VSN) to select relevant input features at each step.
    Optimized for high-dimensional feature spaces to prevent parameter blow-up.
    """
    def __init__(self, num_features: int, d_model: int, dropout: float = 0.1):
        super().__init__()
        self.num_features = num_features
        self.d_model = d_model
        
        # Bottleneck projection to generate variable weights efficiently
        self.bottleneck = nn.Sequential(
            nn.Linear(num_features * d_model, d_model),
            nn.ELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, num_features)
        )
        
        # Shared GRN for feature processing to save memory and avoid overfitting
        self.shared_grn = GatedResidualNetwork(d_model, dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: [batch, seq_len, num_features, d_model]
        batch_size, seq_len, num_feats, d_model = x.shape
        
        # Flatten features for gating bottleneck: [batch, seq_len, num_features * d_model]
        x_flat = x.reshape(batch_size, seq_len, num_feats * d_model)
        
        # Compute variable selection weights: [batch, seq_len, num_features]
        v_weights = self.bottleneck(x_flat)
        v_weights = torch.softmax(v_weights, dim=-1).unsqueeze(-1) # [batch, seq_len, num_features, 1]
        
        # Process all features through the shared GRN
        # Reshape to apply shared GRN to all features in parallel
        x_reshaped = x.reshape(-1, d_model)
        processed = self.shared_grn(x_reshaped)
        
        # Reshape back: [batch, seq_len, num_features, d_model]
        processed_feats = processed.reshape(batch_size, seq_len, num_feats, d_model)
        
        # Weight features and sum: [batch, seq_len, d_model]
        out = torch.sum(processed_feats * v_weights, dim=2)
        return out

class CustomTemporalFusionTransformer(nn.Module):
    """
    Lightweight, custom Temporal Fusion Transformer (TFT) implementation
    specifically tailored for space weather electron flux multi-horizon regression.
    """
    def __init__(self, num_features: int, d_model: int = 64, nhead: int = 4, 
                 num_layers: int = 2, dropout: float = 0.1, 
                 horizons: list = [30, 45, 360, 720], num_quantiles: int = 3):
        super().__init__()
        self.num_features = num_features
        self.d_model = d_model
        self.horizons = horizons
        self.num_quantiles = num_quantiles
        
        # Feature embeddings projection (vectorized parameters)
        self.feature_weights = nn.Parameter(torch.Tensor(num_features, d_model))
        self.feature_biases = nn.Parameter(torch.Tensor(num_features, d_model))
        
        # Initialize parameters
        nn.init.xavier_uniform_(self.feature_weights)
        nn.init.zeros_(self.feature_biases)
        
        # Variable Selection Network
        self.vsn = VariableSelectionNetwork(num_features, d_model, dropout)
        
        # LSTM context encoder
        self.lstm = nn.LSTM(
            input_size=d_model, 
            hidden_size=d_model, 
            num_layers=num_layers, 
            batch_first=True, 
            dropout=dropout if num_layers > 1 else 0
        )
        
        # Multi-head Self-Attention over time
        self.attention = nn.MultiheadAttention(
            embed_dim=d_model, 
            num_heads=nhead, 
            dropout=dropout, 
            batch_first=True
        )
        self.grn_post_attn = GatedResidualNetwork(d_model, dropout)
        
        # Quantile prediction heads for each forecast horizon
        # Target output shape: [batch, len(horizons), num_quantiles]
        self.regressors = nn.ModuleList([
            nn.Sequential(
                nn.Linear(d_model, d_model // 2),
                nn.ReLU(),
                nn.Linear(d_model // 2, num_quantiles)
            ) for _ in horizons
        ])

    def load_state_dict(self, state_dict, strict=True):
        # Convert state_dict if it has old feature_projections keys
        has_projections = False
        new_state_dict = {}
        weights = {}
        biases = {}
        for k, v in state_dict.items():
            if k.startswith("feature_projections."):
                has_projections = True
                parts = k.split(".")
                idx = int(parts[1])
                param_type = parts[2]
                if param_type == "weight":
                    weights[idx] = v.squeeze(-1)
                elif param_type == "bias":
                    biases[idx] = v
            else:
                new_state_dict[k] = v
        
        if has_projections:
            weight_list = [weights[i] for i in range(self.num_features)]
            bias_list = [biases[i] for i in range(self.num_features)]
            new_state_dict["feature_weights"] = torch.stack(weight_list)
            new_state_dict["feature_biases"] = torch.stack(bias_list)
            
        return super().load_state_dict(new_state_dict, strict=strict)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Raw input features of shape [batch, seq_len, num_features]
        Returns:
            predictions: Quantile predictions of shape [batch, num_horizons, num_quantiles]
        """
        # Vectorized feature projections: [batch, seq_len, num_features, d_model]
        # Broadcasts x [batch, seq_len, num_features, 1] with weights/biases [1, 1, num_features, d_model]
        projected = (
            x.unsqueeze(-1) * self.feature_weights.unsqueeze(0).unsqueeze(0)
            + self.feature_biases.unsqueeze(0).unsqueeze(0)
        )
        
        # VSN selection: [batch, seq_len, d_model]
        selected_feats = self.vsn(projected)
        
        # Local temporal context with LSTM
        lstm_out, _ = self.lstm(selected_feats)
        
        # Long-range dependencies with Self-Attention
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        
        # Skip connection & GRN
        enriched = self.grn_post_attn(lstm_out + attn_out)
        
        # Pooling sequence representation over time steps (use last step or mean)
        seq_rep = enriched[:, -1, :] # [batch, d_model]
        
        # Compute quantile predictions for each horizon
        preds = []
        for reg in self.regressors:
            preds.append(reg(seq_rep).unsqueeze(1)) # [batch, 1, num_quantiles]
            
        predictions = torch.cat(preds, dim=1) # [batch, num_horizons, num_quantiles]
        return predictions
