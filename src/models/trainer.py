import os
import logging
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from typing import Dict, Any, Tuple, Optional

# Setup professional logger
logger = logging.getLogger("SpaceWeatherTrainer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class QuantileLoss(nn.Module):
    """
    Pinball Loss (Quantile Loss) for multi-quantile regression predictions.
    Computes loss across multiple output horizons and target quantiles.
    """
    def __init__(self, quantiles: list = [0.1, 0.5, 0.9]):
        super().__init__()
        self.quantiles = quantiles

    def forward(self, preds: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Args:
            preds: Predictions tensor of shape [batch_size, num_horizons, num_quantiles]
            targets: Targets tensor of shape [batch_size, num_horizons]
        Returns:
            Mean Pinball Loss over all horizons and quantiles.
        """
        losses = []
        for i, q in enumerate(self.quantiles):
            # Target vs prediction for quantile q
            error = targets - preds[:, :, i]
            # Pinball loss formula: max(q * error, (q - 1) * error)
            loss_q = torch.max(q * error, (q - 1) * error)
            losses.append(loss_q.unsqueeze(-1))
            
        # Stack and take mean over horizons, quantiles and batch
        loss_tensor = torch.cat(losses, dim=-1) # [batch, num_horizons, num_quantiles]
        return loss_tensor.mean()

class EarlyStopping:
    """
    Early stopping helper to halt training when validation metric stops improving.
    """
    def __init__(self, patience: int = 5, min_delta: float = 0.0, checkpoint_path: str = "best_model.pt"):
        self.patience = patience
        self.min_delta = min_delta
        self.checkpoint_path = checkpoint_path
        self.counter = 0
        self.best_loss = float('inf')
        self.early_stop = False

    def __call__(self, val_loss: float, model: nn.Module, optimizer: optim.Optimizer, epoch: int):
        if val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.counter = 0
            self.save_checkpoint(model, optimizer, epoch)
        else:
            self.counter += 1
            logger.info(f"EarlyStopping counter: {self.counter} out of {self.patience}")
            if self.counter >= self.patience:
                self.early_stop = True

    def save_checkpoint(self, model: nn.Module, optimizer: optim.Optimizer, epoch: int):
        """Saves model state and optimizer state when validation loss decreases."""
        os.makedirs(os.path.dirname(self.checkpoint_path), exist_ok=True)
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'best_loss': self.best_loss
        }, self.checkpoint_path)
        logger.info(f"Validation loss decreased. Checkpoint saved to: {self.checkpoint_path}")

class SpaceWeatherTrainer:
    """
    Unified training engine for SWEWS. Provides methods to train either:
    1. Model 1: Transformer Encoder Classifier (Cross-Entropy Loss with optional weights)
    2. Model 2: Custom TFT Regressor (Quantile / Pinball Loss)
    """
    def __init__(self, device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"SpaceWeatherTrainer initialized on device: {self.device}")

    def _log_batch_progress(self, batch_idx: int, total_batches: int, prefix: str) -> None:
        if total_batches <= 0:
            return
        checkpoints = {0, max(0, total_batches // 4), max(0, total_batches // 2), max(0, (3 * total_batches) // 4), total_batches - 1}
        if batch_idx in checkpoints:
            logger.info("%s batch %s/%s", prefix, batch_idx + 1, total_batches)

    def train_epoch_classifier(self, model: nn.Module, dataloader: DataLoader, 
                               optimizer: optim.Optimizer, criterion: nn.Module) -> float:
        model.train()
        total_loss = 0.0
        total_batches = len(dataloader)
        
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            self._log_batch_progress(batch_idx, total_batches, "Classifier train")
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            
            optimizer.zero_grad()
            logits = model(inputs)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item() * inputs.size(0)
            
        return total_loss / len(dataloader.dataset)

    @torch.no_grad()
    def validate_epoch_classifier(self, model: nn.Module, dataloader: DataLoader, 
                                  criterion: nn.Module) -> float:
        model.eval()
        total_loss = 0.0
        total_batches = len(dataloader)
        
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            self._log_batch_progress(batch_idx, total_batches, "Classifier val")
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            logits = model(inputs)
            loss = criterion(logits, targets)
            total_loss += loss.item() * inputs.size(0)
            
        return total_loss / len(dataloader.dataset)

    def train_classifier(self, model: nn.Module, train_loader: DataLoader, 
                         val_loader: DataLoader, epochs: int = 50, 
                         lr: float = 1e-3, weight_decay: float = 1e-4, 
                         class_weights: Optional[torch.Tensor] = None, 
                         patience: int = 7, checkpoint_dir: str = "saved_models") -> Dict[str, Any]:
        """
        Train the Transformer Encoder Classifier.
        """
        model = model.to(self.device)
        optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
        
        # Use Weighted CrossEntropy for severe class imbalance
        if class_weights is not None:
            class_weights = class_weights.to(self.device)
        criterion = nn.CrossEntropyLoss(weight=class_weights)
        
        early_stopping = EarlyStopping(
            patience=patience, 
            checkpoint_path=os.path.join(checkpoint_dir, "best_classifier.pt")
        )
        
        history = {"train_loss": [], "val_loss": []}
        logger.info("Starting Transformer Classifier Training...")
        
        for epoch in range(1, epochs + 1):
            train_loss = self.train_epoch_classifier(model, train_loader, optimizer, criterion)
            val_loss = self.validate_epoch_classifier(model, val_loader, criterion)
            
            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            
            logger.info(f"Epoch {epoch:02d}/{epochs:02d} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
            
            early_stopping(val_loss, model, optimizer, epoch)
            if early_stopping.early_stop:
                logger.info("Early stopping triggered. Training stopped.")
                break
                
        return history

    def train_epoch_regressor(self, model: nn.Module, dataloader: DataLoader, 
                             optimizer: optim.Optimizer, criterion: nn.Module) -> float:
        model.train()
        total_loss = 0.0
        total_batches = len(dataloader)
        
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            self._log_batch_progress(batch_idx, total_batches, "Regressor train")
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            
            optimizer.zero_grad()
            predictions = model(inputs)
            loss = criterion(predictions, targets)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item() * inputs.size(0)
            
        return total_loss / len(dataloader.dataset)

    @torch.no_grad()
    def validate_epoch_regressor(self, model: nn.Module, dataloader: DataLoader, 
                                criterion: nn.Module) -> float:
        model.eval()
        total_loss = 0.0
        total_batches = len(dataloader)
        
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            self._log_batch_progress(batch_idx, total_batches, "Regressor val")
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            predictions = model(inputs)
            loss = criterion(predictions, targets)
            total_loss += loss.item() * inputs.size(0)
            
        return total_loss / len(dataloader.dataset)

    def train_regressor(self, model: nn.Module, train_loader: DataLoader, 
                        val_loader: DataLoader, epochs: int = 50, 
                        lr: float = 1e-3, weight_decay: float = 1e-4, 
                        quantiles: list = [0.1, 0.5, 0.9], 
                        patience: int = 7, checkpoint_dir: str = "saved_models") -> Dict[str, Any]:
        """
        Train the Custom Temporal Fusion Transformer Regressor.
        """
        model = model.to(self.device)
        optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
        criterion = QuantileLoss(quantiles)
        
        early_stopping = EarlyStopping(
            patience=patience, 
            checkpoint_path=os.path.join(checkpoint_dir, "best_tft_regressor.pt")
        )
        
        history = {"train_loss": [], "val_loss": []}
        logger.info("Starting Temporal Fusion Transformer Regression Training...")
        
        for epoch in range(1, epochs + 1):
            train_loss = self.train_epoch_regressor(model, train_loader, optimizer, criterion)
            val_loss = self.validate_epoch_regressor(model, val_loader, criterion)
            
            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            
            logger.info(f"Epoch {epoch:02d}/{epochs:02d} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
            
            early_stopping(val_loss, model, optimizer, epoch)
            if early_stopping.early_stop:
                logger.info("Early stopping triggered. Training stopped.")
                break
                
        return history
