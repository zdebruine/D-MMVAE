import torch

def kl_divergence(mu, logvar):
    """
    Calculate the KL divergence between a given Gaussian distribution q(z|x)
    and the standard Gaussian distribution p(z).

    Parameters:
    - mu (torch.Tensor): The mean of the Gaussian distribution q(z|x).
    - sigma (torch.Tensor): The standard deviation of the Gaussian distribution q(z|x).

    Returns:
    - torch.Tensor: The KL divergence.
    """
    return -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())

def cyclic_annealing(batch_iteration, cycle_length, min_beta=0.0, max_beta=1.0, ceil_downswings=True, floor_upswings=False):
    """
    Calculates the cyclic annealing rate based on the current batch iteration.
    
    Parameters:
    - batch_iteration: Current batch iteration in the training process.
    - cycle_length: Number of batch iterations in a full cycle.
    - min_beta: Minimum value of the annealing rate.
    - max_beta: Maximum value of the annealing rate.
    - ceil_upswings: Keeps downswings at max_beta.
    - floor_upswings: Keeps upswings at min_beta.
    
    Returns:
    - beta_value: The calculated annealing rate for the current batch iteration.
    """
    
    
    
    # Determine the current position in the cycle
    cycle_position = batch_iteration % cycle_length
    
    # Calculate the phase of the cycle (upswing or downswing)
    if cycle_position < cycle_length / 2:
        if floor_upswings:
            return min_beta
        # Upswing phase
        return min_beta + (max_beta - min_beta) * (2 * cycle_position / cycle_length)
    else:
        if ceil_downswings:
            return max_beta
        # Downswing phase
        return max_beta - (max_beta - min_beta) * (2 * (cycle_position - cycle_length / 2) / cycle_length)

def calculate_r2(input: torch.Tensor, target: torch.Tensor) -> float:
    """
    Calculates the R^2 score indicating how well the target reconstructs the input.

    Parameters:
    - input: torch.Tensor representing the original data.
    - target: torch.Tensor representing the reconstructed or predicted data.

    Returns:
    - R^2 score as a float.
    """
    # Ensure input and target have the same shape
    if input.shape != target.shape:
        raise ValueError("Input and target tensors must have the same shape")

    # Calculate the mean of the original inputs
    mean_input = input.mean()

    # Calculate SS_tot (total sum of squares of difference from the mean)
    ss_tot = torch.sum((input - mean_input) ** 2)

    # Calculate SS_res (sum of squares of the residuals between input and target)
    ss_res = torch.sum((input - target) ** 2)

    # Calculate and return the R^2 score
    r2_score = 1 - ss_res / ss_tot
    return r2_score.item()