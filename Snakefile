## Snakemake workflow for the CMMVAE (Conditional Multimodal Variational Autoencoder) module.
## This workflow automates the training, merging, and evaluation processes for CMMVAE models.

## Import necessary libraries and modules.
from snakemake.utils import validate
import os

## Load the configuration file specified for this workflow.
configfile: "workflow/config.yaml"

## Validate the configuration file against a predefined schema to ensure correctness and completeness.
validate(config, "workflow/config.schema.yaml")

## Define the root directory for the experiment, extracted from the configuration file.
## This directory serves as the main folder where all experiment-related outputs will be stored.
ROOT_DIR = config["root_dir"]

## Define the name of the experiment, extracted from the configuration file.
## This name is used to distinguish between different experiments within the root directory.
EXPERIMENT_NAME = config["experiment_name"]

## Define the name of the specific run within the experiment. If not provided, defaults to "default_run".
RUN_NAME = config.get("run_name", "default_run")

## Define the directory path where this specific run's results will be stored.
RUN_DIR = os.path.join(ROOT_DIR, EXPERIMENT_NAME, RUN_NAME)

## Define the name of the configuration file specific to this run. Defaults to "config.yaml" if not specified.
CONFIG_NAME = config.get("config_name", "config.yaml")

## Define the keys that are used for merging results from different experiments.
MERGE_KEYS = config["merge_keys"]

## Define the categories for which UMAP visualizations will be generated.
## This is optional, and if not provided, defaults to an empty list.
CATEGORIES = config.get("categories", [])

## Define the directory where UMAP visualizations will be saved.
## Defaults to "umap" within the run directory.
UMAP_PATH = config.get("umap_dir", "umap")
UMAP_DIR = os.path.join(RUN_DIR, UMAP_PATH)

## Define the directory to store correlation outputs
CORRELATION_PATH = config.get("correlation_dir", "correlations")
CORRELATION_DIR = os.path.join(RUN_DIR, CORRELATION_PATH)

CORRELATION_DATA = config["correlation_data"]

## Generate the paths for the embeddings and metadata files based on the merge keys.
EMBEDDINGS_PATHS = [os.path.join(MERGED_DIR, f"{key}_embeddings.npz") for key in MERGE_KEYS]
METADATA_PATHS = [os.path.join(MERGED_DIR, f"{key}_metadata.pkl") for key in MERGE_KEYS]

## Define the path to the training configuration file within the run directory.
TRAIN_CONFIG_FILE = os.path.join(RUN_DIR, CONFIG_NAME)

## Define the path to the checkpoint file for saving the best model.
CKPT_PATH = os.path.join(RUN_DIR, "checkpoints", "best_model.ckpt")

## Optional: Set a seed value for reproducibility. If not specified, the seed is set to False.
## This ensures that the results can be replicated exactly in subsequent runs.
SEED = config.get('seed', False)

## Generate file paths for UMAP evaluation images using the configured directory structure.
EVALUATION_FILES = expand(
    "{root_dir}/{experiment}/{run}/{results}/integrated.{category}.umap.{key}.png",
    root_dir=ROOT_DIR,
    experiment=EXPERIMENT_NAME,
    run=RUN_NAME,
    category=CATEGORIES,
    results=UMAP_PATH,
    key=MERGE_KEYS,
)


## Construct the command to run the CMMVAE training pipeline.
## If a configuration directory is provided, it is included in the command; otherwise,
## individual parameters such as trainer, model, and data are passed explicitly.
TRAIN_COMMAND = config["train_command"]
CORRELATION_COMMAND = config["correlation_command"]

# TODO: Avoid automatic conditionals
TRAIN_COMMAND += str(
    f" --default_root_dir {ROOT_DIR} "
    f"--experiment_name {EXPERIMENT_NAME} --run_name {RUN_NAME} "
    f"--seed_everything {SEED} "
    f"--predict_dir {PREDICT_SUBDIR} "
)

CATEGORIES_COMMAND = " ".join(f"--categories {category}" for category in CATEGORIES)
MERGE_KEY_COMMAND = " ".join(f"--keys {merge_key}" for merge_key in MERGE_KEYS)

## Allow for easy reuse of configurations depending on the run directory
# Optional flag "override" to override previous configurations
# The config dictionary is stored in the run directory so this needs
# to be the last step to make sure any changes to the config are store in configuration
# and reflected in the rules. The only modifications to the configuration values
# that are acceptable is to configure them for passing as arguments to the rule commands
# SNAKEMAKE_CONFIG_PATH = os.path.join(RUN_DIR, "snakemake.config")
# OVERRIDE_CONFIG = config.get(" override", None)

# if os.path.exists(SNAKEMAKE_CONFIG_PATH):

# need to check this before parsing all the rules to set config.
# need to move all default values to live in configuration as well so that they are picked up in
# config file

## Define the final output rule for Snakemake, specifying the target files that should be generated
## by the end of the workflow.
rule all:
    input:
        EVALUATION_FILES,
        MD_FILES

## Define the rule for finding unique expressions for conditional layers
## The output includes paths to the conditional layer expressions used.
rule diff_expression:
    output:
        os.path.join(RUN_DIR, "expression_complete.log")
    params:
        cli=TRAIN_COMMAND.lstrip('fit'),
    shell:
        """
        cmmvae workflow expression {params.cli}
        touch {output}
        """

## Define the rule for training the CMMVAE model.
## The output includes the configuration file, the checkpoint path.
rule train:
    input:
        rules.diff_expression.output
    output:
        ckpt_path=CKPT_PATH,
    params:
        command=TRAIN_COMMAND
    shell:
        """
        cmmvae workflow cli {params.command}
        """

## Define the rule for running predictions if necessary
## The output includes the predictions path.
rule predict:
    input:
        ckpt_path=CKPT_PATH,
    output:
        os.path.join(RUN_DIR, "predictions.h5")
    params:
        command=TRAIN_COMMAND.lstrip('fit')
    shell:
        """
        cmmvae workflow cli predict {params.command} --ckpt_path {input.ckpt_path}
        """

## Define the rule for getting R^2 correlations on the filtered data
## This rule outputs correlation scores per filtered data group
rule correlations:
    input:
        embeddings_path=EMBEDDINGS_PATHS,
    output:
        CORRELATION_FILES,
    params:
        command=CORRELATION_COMMAND,
        data=CORRELATION_DATA,
        save_dir=CORRELATION_DIR,
    shell:
        """
        mkdir -p {CORRELATION_DIR}
        cmmvae workflow correlations {params.command} --correlation_data {params.data} --save_dir {params.save_dir}
        """

## Define the rule for generating UMAP visualizations from the merged predictions.
## This rule produces UMAP images for each combination of category and merge key.
rule umap_predictions:
    input:
        rules.predict.output
    output:
        EVALUATION_FILES,
    params:
        save_dir=UMAP_DIR,
        categories=CATEGORIES_COMMAND,
        merge_keys=MERGE_KEY_COMMAND,
    shell:
        """
        cmmvae workflow umap-predictions --directory {input} {params.categories} {params.merge_keys} --save_dir {params.save_dir}
        """

rule meta_discriminators:
    input:
        CKPT_PATH
    output:
        MD_FILES,
    params:
        log_dir=META_DISC_DIR,
        ckpt=CKPT_PATH,
        config=TRAIN_CONFIG_FILE
    shell:
        """
        cmmvae workflow meta-discriminator --log_dir {params.log_dir} --ckpt {params.ckpt} --config {params.config}
        """
