import os
import subprocess
import sys
import logging
from datetime import datetime

# Configuration
LOCAL_REPO_PATH = '/usr/lib/perl5/vendor_perl/auto/SVN/_Repos/my project'  # Change this to your local repo path
REMOTE_REPO_URL = 'https://github.com/srishti10-g/project.git'  # Change this to your remote repo URL
BRANCH_NAME = 'main'  # Change this to your branch name
LOG_FILE = 'repo_sync.log'  # Log file name

# Set up logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def run_command(command, cwd=None):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logging.info(f"Command executed: {' '.join(command)}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing command: {' '.join(command)} - {e.stderr.strip()}")
        print(f"Error: {e.stderr.strip()}")
        sys.exit(1)

def check_git_repo():
    """Check if the current directory is a git repository."""
    if not os.path.isdir(os.path.join(LOCAL_REPO_PATH, '.git')):
        logging.error(f"{LOCAL_REPO_PATH} is not a git repository.")
        print(f"{LOCAL_REPO_PATH} is not a git repository.")
        sys.exit(1)

def pull_changes():
    """Pull changes from the remote repository."""
    print("Pulling changes from remote repository...")
    run_command(['git', 'pull', 'origin', BRANCH_NAME], cwd=LOCAL_REPO_PATH)

def add_changes():
    """Add changes to the staging area."""
    print("Adding changes to staging area...")
    run_command(['git', 'add', '.'], cwd=LOCAL_REPO_PATH)

def commit_changes():
    """Commit changes to the local repository."""
    print("Committing changes...")
    run_command(['git', 'commit', '-m', 'Automated sync commit'], cwd=LOCAL_REPO_PATH)

def push_changes():
    """Push changes to the remote repository."""
    print("Pushing changes to remote repository...")
    run_command(['git', 'push', 'origin', BRANCH_NAME], cwd=LOCAL_REPO_PATH)

def check_branch():
    """Check the current branch and switch if necessary."""
    current_branch = run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=LOCAL_REPO_PATH)
    if current_branch != BRANCH_NAME:
        print(f"Switching from branch '{current_branch}' to '{BRANCH_NAME}'...")
        run_command(['git', 'checkout', BRANCH_NAME], cwd=LOCAL_REPO_PATH)

def log_status():
    """Log the current status of the repository."""
    status = run_command(['git', 'status'], cwd=LOCAL_REPO_PATH)
    logging.info(f"Repository status:\n{status}")

def main():
    """Main function to synchronize the repository."""
    check_git_repo()
    
    # Log the start of the synchronization process
    logging.info("Starting repository synchronization.")
    
    # Pull the latest changes from the remote repository
    pull_changes()
    
    # Log the current status of the repository
    log_status()
    
    # Check for changes in the local repository
    if run_command(['git', 'status', '--porcelain'], cwd=LOCAL_REPO_PATH):
        add_changes()
        commit_changes()
        push_changes()
    else:
        print("No changes to commit.")
        logging.info("No changes to commit.")

    # Log the end of the synchronization process
    logging.info("Repository synchronization completed.")

if __name__ == "__main__":
    main()