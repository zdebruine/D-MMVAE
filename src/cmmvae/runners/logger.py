"""
    Review snakemake job file outputs and history.
"""
from typing import Callable, Literal, Optional, Union
import click
import os
import re
import time

SUBMISSION_REGEX = (
    r'rule (\w+):.*?'
    r'Submitted job (\d+)'
    r' with external jobid \'(\d+)\''
)


def scan_file(out_file: str):
    with open(out_file, 'r') as f:
        while True:
            line = f.readline()
            if line:
                click.echo(line, nl=False)
            else:
                time.sleep(1)


def _parse_submission_file(log_file):
    """
    Parses snakemake head node (submission) stderr output file
    for rules that have been executed along with the job id for each rule.

    Args:
        log_file (str): Path to the submission log file to parse.

    Returns:
        dict[str, int]: Dictionary of rules and their respective job ids.
    """
    rules = {}
    with open(log_file, 'r') as f:
        content = f.read()
        # Regex to find all rule blocks
        rule_blocks = re.findall(SUBMISSION_REGEX, content, re.DOTALL)
        # Parse just the rule ran and the rule_job_id's
        for rule, _, rule_job_id in rule_blocks:
            rules[rule] = rule_job_id
    return rules


def default_quit_callback():
    click.echo("Exiting...")
    exit(0)


class Prompts:

    @classmethod
    def prompt_with_callbacks(
        cls,
        prompt_callback: Callable,
        quit_callback: Callable = default_quit_callback,
        back_callback: Optional[Callable] = None,
        valid_results: list = [],
    ):
        assert isinstance(valid_results, (list, tuple))
        assert all(isinstance(result, (str)) for result in valid_results)

        valid = False
        while not valid:
            result = prompt_callback()
            lower_result = str(result).lower()
            if quit_callback and lower_result in ("q", "quit"):
                quit_callback and quit_callback()
            elif back_callback and lower_result in ("b", "back"):
                back_callback()
            elif not valid_results or result in valid_results:
                valid = True
            else:
                click.echo("Input is not valid!")
                click.echo(f"Valid: {valid_results}")
        return result

    @classmethod
    def prompt_jobid(cls):
        return click.prompt("Enter a valid job ID", type=str)

    @classmethod
    def prompt_file(cls):
        return click.prompt("Select file type to monitor (out/err)",
                            type=str, default="err")


def display_job_tree(job_id: str, rules: dict):
    click.echo(f'Job: {job_id}')
    for i, (rule, rule_job_id) in enumerate(rules.items()):
        click.echo(f'  └── Rule: {rule} (Job ID: {rule_job_id})')


def record_view_history():
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # Check if the attribute exists, if not, initialize it
            print(f"Adding view to history: {func.__name__} {args}, {kwargs}")
            self._view_history.append((func.__name__, (args, kwargs)))
            # Call the original method
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def get_files(rule_dir, starts_with: str = 'job.', ends_with: str = '.err'):
    return [
        f for f in os.listdir(rule_dir)
        if f.startswith(starts_with) and f.endswith(ends_with)
    ]


def get_job_numbers(err_files: list[str]):
    job_numbers = []
    for f in err_files:
        matches = re.search(r'job\.(\d+)\.err', f)
        if matches:
            job_numbers.append(matches.group(1))
    return job_numbers


def get_last_job_id(rule_dir: str) -> Optional[str]:

    err_files = get_files(rule_dir)
    if not err_files:
        return None

    # Extract job numbers and find the highest
    job_numbers = get_job_numbers(err_files)
    last_job_number = max(job_numbers)

    return last_job_number


def get_last_n_job_ids(rule_dir: str, n: int):
    err_files = get_files(rule_dir)

    job_numbers = sorted(get_job_numbers(err_files), reverse=True)
    return job_numbers[:n]


class Logger:

    def __init__(self, log_dir):
        self.log_dir = log_dir
        self._view_history = []

    def invoke_last_view(self):

        if not self._view_history:
            exit(1)

        view_info = self._view_history.pop()

        self._invoke_view(view_info[0], *view_info[1][0], **view_info[1][1])

    def _invoke_view(self, view: str, *args, **kwargs):

        view_fn = getattr(self, view)
        view_fn(*args, **kwargs)

    def get_path(
        self,
        rule: Optional[str] = None,
        job_id: Optional[int] = None,
        file_type: Optional[Union[Literal['err'], Literal['out']]] = None
    ):
        if file_type and not (job_id and rule):
            raise ValueError(
                f"Attempting to access file_type '{file_type}'"
                " with either no job_id or rule."
            )
        elif job_id and not rule:
            raise ValueError(
                f"Attempting to acces job_id {job_id} with no rule"
            )

        return os.path.join(self.log_dir, *(
            rule if rule else "",
            f'job.{job_id}.{file_type}'
            if job_id and file_type and rule else ""
        ))

    def get_submission_log_file(self, job_id):
        return self.get_path('submission', job_id, 'err')

    def parse_submission_file(self, submission_jobid: Optional[str] = None):
        submission_dir = self.get_path('submission')
        submission_jobid = submission_jobid or get_last_job_id(submission_dir)
        log_file = self.get_submission_log_file(submission_jobid)
        rules = _parse_submission_file(log_file)
        return rules

    def back_callback(self):
        if self._view_history:
            self._view_history.pop()
            self.invoke_last_view()
        else:
            raise RuntimeError("")

    def prompt_user(self, callback, *args, **kwargs):
        return Prompts.prompt_with_callbacks(
            prompt_callback=callback,
            back_callback=self.back_callback,
            *args, **kwargs
        )

    def prompt_back(self):
        while self._view_history:
            prev_view_name = str(self._view_history[-1][0]).replace('_', ' ')
            if click.confirm(f"Would you like to return to {prev_view_name}?", default=False):
                self.invoke_last_view()
            else:
                self._view_history.pop()

    @record_view_history()
    def view_history(self, n: int):
        submission_dir = self.get_path('submission')
        submission_jobs = get_last_n_job_ids(submission_dir, n)

        submission_job_rules = {}
        valid_results = list(submission_jobs)
        for submission_jobid in submission_jobs:
            rules = self.parse_submission_file(submission_jobid)
            submission_job_rules[submission_jobid] = rules
            valids = list(submission_job_rules[submission_jobid].values())
            valid_results.extend(valids)
            display_job_tree(submission_jobid, rules)

        result = self.prompt_user(
            Prompts.prompt_jobid, valid_results=valid_results
        )

        if result in submission_jobs:
            self.view_submission(result)
        else:
            for submission_jobid, rules in submission_job_rules.items():
                for rule, rule_jobid in rules.items():
                    if result == rule_jobid:
                        self.view_file_type(rule, rule_jobid)
                        return

    @record_view_history()
    def view_submission(self, submission_jobid: Optional[str] = None):
        submission_dir = self.get_path('submission')
        submission_jobid = submission_jobid or get_last_job_id(submission_dir)
        if not submission_jobid:
            raise RuntimeError("submission_jobid is None!")
        rules = self.parse_submission_file(submission_jobid)
        display_job_tree(submission_jobid, rules)
        self.view_navigate_submission_rules(rules)

    def view_navigate_submission_rules(self, rules: dict):

        valid_results = []
        jobids_to_rule = {
            value: key
            for key, value, in rules.items()
        }

        valid_results = list(rules.keys()) + list(rules.values())
        result = self.prompt_user(
            Prompts.prompt_jobid, valid_results=valid_results
        )

        rule = result if result in rules else jobids_to_rule[result]
        rule_jobid = result if result in jobids_to_rule else rules[result]

        file_type = self.prompt_user(
            Prompts.prompt_file, valid_results=('out', 'err')
        )
        self.view_rule_files(rule, rule_jobid, file_type)

    @record_view_history()
    def view_file_type(self, rule, rule_jobid):
        file_type = self.prompt_user(
            Prompts.prompt_file, valid_results=('out', 'err')
        )
        self.view_rule_files(rule, rule_jobid, file_type)

    def view_rule_files(self, rule, rule_jobid, file_type):

        out_file = self.get_path(rule, rule_jobid, file_type)

        if os.path.exists(out_file):
            click.echo(
                f"File for rule '{rule}'"
                f" with job ID {rule_jobid}"
                f" not found: {out_file}"
            )
            return

        if os.path.getsize(out_file) == 0:
            click.echo("File is empty!")
            return

        try:
            scan_file(out_file)
        except KeyboardInterrupt:
            click.echo("Aborting scan...")

        self.prompt_back()


@click.group()
def logger():
    """Logger command group."""
    pass


@logger.command()
@click.option('--log_dir', type=click.Path(), default="./.cmmvae/logs",
              show_default=True, help="Directory where logs are stored.")
def last(log_dir):
    """View the last job or a specified job."""
    Logger(log_dir).view_submission()


@logger.command()
@click.option('--log_dir', type=click.Path(), default="./.cmmvae/logs",
              show_default=True, help="Directory where logs are stored.")
@click.option('--job-id', type=str, default=None,
              help='Specify a job ID to view details.')
def job(log_dir, job_id):
    Logger(log_dir).view_submission(job_id)


@logger.command()
@click.option('-n', type=int, default=3,
              help='Number of jobs to display in history.')
@click.option('--log_dir', type=click.Path(), default="./.cmmvae/logs",
              show_default=True, help="Directory where logs are stored.")
def history(**kwargs):
    """Display the last n jobs in history."""
    Logger(kwargs['log_dir']).view_history(kwargs['n'])


if __name__ == '__main__':
    logger()
