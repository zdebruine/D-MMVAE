import umap
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import torch
import os
import random

import argparse
from PIL import Image

from torch.utils.tensorboard import SummaryWriter


def plot_umap(
    npz_path, 
    meta_path, 
    save_path, 
    n_neighbors = 30,
    min_dist = 0.3,
    n_components = 2,
    metric = "cosine",
    low_memory = False,
    n_jobs = 40,
    n_epochs = 200,
    n_largest = 15,
    categories = ['cell_type', 'dataset_id', 'assay', 'donor_id'],
    umap_embeddings: bool = False,
    method: str = None,
    **umap_kwargs,
):
    
    name = os.path.basename(npz_path).removesuffix('_embeddings.npz')
    X = np.load(npz_path)['embeddings']
    metadata = pd.read_pickle(meta_path)

    if umap_embeddings:
        embedding = X
    else:
        # Fit and transform the data using UMAP
        reducer = umap.UMAP(
            n_neighbors=n_neighbors, 
            min_dist=min_dist, 
            n_components=n_components,
            metric=metric, 
            low_memory=low_memory, 
            n_jobs=n_jobs, 
            n_epochs=n_epochs, 
            **umap_kwargs)
        
        embedding = reducer.fit_transform(X)
        np.savez(os.path.join(save_path, 'umap_embeddings.npz'), embeddings=embedding)
        metadata.to_pickle(os.path.join(save_path, 'umap_metadata.pkl'))
    
    image_paths = []
    for category in categories:
        image_path = plot_category(embedding, metadata, category, save_path, n_largest, name, method)
        image_paths.append(image_path)
    return image_paths

def plot_category(embedding, metadata, category, save_path, n_largest, name, method, alpha=0.5, marker_size=1):
    plt.figure(figsize=(14, 8))
    unique_values = metadata[category].value_counts().nlargest(n_largest).index
    
    # Prepare color map
    cmap = plt.get_cmap('nipy_spectral', len(unique_values))
    color_list = [cmap(i) for i in range(len(unique_values))]
    
    # Combine embedding and metadata into a DataFrame
    df = pd.DataFrame(embedding, columns=['x', 'y'])
    df[category] = metadata[category].values
    
    # Filter to include only the largest categories
    df = df[df[category].isin(unique_values)]
    
    # Shuffle the DataFrame to randomize the plotting order
    df = df.sample(frac=1).reset_index(drop=True)
    
    # Create a dictionary to map categories to colors
    category_to_color = {value: color_list[i] for i, value in enumerate(unique_values)}
    
    # Map colors to the entire DataFrame
    df['color'] = df[category].map(category_to_color)
    
    # Plot all points in the shuffled order with specified opacity and marker size
    plt.scatter(df['x'], df['y'], c=df['color'], s=marker_size, alpha=alpha)
    
    if method:
        method = f" for {method} "
    else:
        method = " "
    
    plt.title(f'UMAP projection{method}colored by {category}')
    
    # Custom legend with a circle for each label
    legend_handles = [plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=cmap(i), markersize=10, label=label)
                      for i, label in enumerate(unique_values)]
    plt.legend(handles=legend_handles, title=category, bbox_to_anchor=(1.05, 1), loc='upper left')
    image_path = os.path.join(save_path, f"integrated.{category}.umap.{name}.png")
    plt.savefig(image_path, bbox_inches='tight')
    plt.close()
    return image_path

def add_images_to_tensorboard(log_dir, image_paths):
    
    writer = SummaryWriter(log_dir=log_dir)
    
    for image_path in image_paths:
        image = Image.open(image_path)
        image = np.array(image)
        image = torch.tensor(image).permute(2, 0, 1)
        tag = os.path.basename(image_path)
        writer.add_image(tag, image, global_step=0)
    writer.close()

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='UMAP Projection Plotting')
    parser.add_argument('-d', '--directory', type=str, required=True, help="Directory of run")
    parser.add_argument('-e', '--embedding_paths', type=str, nargs='+', default=[], help="Name of embedding file")
    parser.add_argument('-m', '--metadata_paths', type=str, nargs='+', default=[], help="Name of metadata file")
    parser.add_argument('--method', type=str, help="Method name to add to graph title")
    parser.add_argument('--skip_tensorboard', action='store_true')
    parser.add_argument('-u', '--umap_embeddings', action='store_true', help="Path to umap embeddings")
    args = parser.parse_args() 
    
    npz_paths = args.embedding_paths
    meta_paths = args.metadata_paths
    
    if not npz_paths or not meta_paths:
        raise RuntimeError("Files not found and are empty")
    
    for npz_path, meta_path in zip(npz_paths, meta_paths):
        
        image_paths = plot_umap(npz_path, meta_path, args.directory, umap_embeddings=args.umap_embeddings, method=args.method)

        if not args.skip_tensorboard:
            add_images_to_tensorboard(args.directory, image_paths)
