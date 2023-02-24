from config import *
from models import BaseLineModel
from utils import TrafficVolumeGraphDataLoader, EarlyStopper

from os.path import isfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from tqdm import tqdm
import torch
import torch.nn as nn
from torch.optim import Adam
from torchinfo import summary

from torch_geometric.nn import GCN, GCNConv, Sequential, GATConv

class GCNModel(nn.Module):
    def __init__(self, num_node_features=4):
        super().__init__()
        self.conv1 = GCNConv(num_node_features, 128) 
        self.conv2 = GCNConv(128, 64)
        self.conv3 = GCNConv(64, 1)

    def forward(self, data):
        x, edge_index, edge_weight = data.x, data.edge_index, data.edge_weight
        x = self.conv1(x, edge_index, edge_weight)
        x = x.relu() 
        #x = F.dropout(x, p=0.5, training=self.training)
        x = self.conv2(x, edge_index, edge_weight)
        x = x.relu() 
        x = self.conv3(x, edge_index, edge_weight)
        return x

if "cuda" in device and not torch.cuda.is_available():
    print(f"Warning: Device set to {device} in config but no GPU available. Using CPU instead.")
    device = "cpu"
    num_workers = 4

lr = 0.001 
batch_size = 128 
epochs = config_baseline["epochs"]

train_dataloader = TrafficVolumeGraphDataLoader(train_data_file, stations_data_file, stations_included_file, graph_file, batch_size=batch_size, num_workers=num_workers, shuffle=True, drop_last=True)
val_dataloader = TrafficVolumeGraphDataLoader(val_data_file, stations_data_file, stations_included_file, graph_file, batch_size=batch_size, num_workers=num_workers, shuffle=False, drop_last=False)
test_dataloader = TrafficVolumeGraphDataLoader(test_data_file, stations_data_file, stations_included_file, graph_file, batch_size=batch_size, num_workers=num_workers, shuffle=False, drop_last=False)

val_steps = len(train_dataloader) // validations_per_epoch 

model = GCNModel().to(device)
loss_function = nn.L1Loss()
optimizer = Adam(model.parameters(), lr=lr) 
earlystopper = EarlyStopper(limit=config_baseline["earlystop_limit"])

train_history = {"train_loss" : [], "val_loss" : []}

for epoch in range(epochs):
    train_losses = []
    for i, data in enumerate((pbar := tqdm(train_dataloader))):
        data = data.to(device)
        
        # Train step
        optimizer.zero_grad()
        pred = model(data).squeeze(1)
        loss = loss_function(pred, data.y)
        loss.backward()
        optimizer.step()
        train_losses.append(loss.item())

        if i % val_steps == val_steps - 1:
            mean_train_loss = np.mean(train_losses)
            train_losses = []
            model.eval()
            val_losses = []
            with torch.no_grad():
                for data in val_dataloader:
                    data = data.to(device)
                    preds = model(data).squeeze(1)
                    val_loss = loss_function(preds, data.y).item()
                    val_losses.append(val_loss)
            mean_val_loss = np.mean(val_losses)
            if earlystopper(mean_val_loss):
                print(f"Early stopped at epoch {epoch}!")
                break
            model.train()
            train_history["train_loss"].append(mean_train_loss)
            train_history["val_loss"].append(mean_val_loss)
            pbar_str = f"Epoch {epoch:02}/{epochs:02} | Loss (Train): {mean_train_loss:.4f} | Loss (Val): {mean_val_loss:.4f} | ES: {earlystopper.counter:02}/{earlystopper.limit:02}"
            pbar.set_description(pbar_str)
    else:
        continue
    break   # Break on early stop

# Save loss plot
fig, axes = plt.subplots(nrows=1, ncols=2)
axes[0].plot(train_history["train_loss"])
axes[0].title.set_text("Training L1-Loss")
axes[0].set_yscale('log')
axes[1].plot(train_history["val_loss"])
axes[1].title.set_text("Validation L1-Loss")
axes[1].set_yscale('log')
fig.tight_layout()
plt.savefig("figs/gnn_training_plot.png", dpi=200)

