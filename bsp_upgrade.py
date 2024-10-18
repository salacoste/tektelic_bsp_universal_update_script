import paramiko
import os
import time

# Configuration details (replace with actual values)
GATEWAY_IP = 'ip_address_of_the_gateway'
GATEWAY_USERNAME = 'root'
GATEWAY_PASSWORD = 'your_password'
LOCAL_BSP_PATH = '/Users/testUser/BSP_7.1.2.zip'
REMOTE_BSP_DIR = '/lib/firmware/bsp/'
REMOTE_SNMP_CONF_DIR = '/etc/opkg/snmpManaged-feed.conf'
SUDO_PASSWORD = GATEWAY_PASSWORD  # Use gateway password for sudo

# Intermediate upgrades
INTERMEDIATE_UPGRADES = {
    "1.6.5": ["3.1.5", "4.0.3"],
    "3.1.5": ["4.0.3"],
    "4.0.3": ["5.x.x"]
}

# Helper function to execute SSH commands and handle errors, with optional sudo support
def execute_command(ssh, command, use_sudo=False):
    # Add 'sudo' if needed and current user is not root
    if use_sudo and GATEWAY_USERNAME != 'root':
        command = f"echo {SUDO_PASSWORD} | sudo -S {command}"
    
    stdin, stdout, stderr = ssh.exec_command(command)
    err = stderr.read().decode()
    if err:
        raise Exception(f"Command failed: {command}\nError: {err}")
    return stdout.read().decode()

# Check current BSP version
def check_bsp_version(ssh):
    version = execute_command(ssh, 'system_version', use_sudo=True).strip()
    print(f"Current BSP Version: {version}")
    return version

# Check available disk space on a specific partition
def check_available_space(ssh, partition='/'):
    command = f'df -h {partition}'
    output = execute_command(ssh, command, use_sudo=True).strip().splitlines()

    print(f"Raw output of 'df -h {partition}':")
    for line in output:
        print(line)

    headers = output[0].split()
    space_info = output[1].split()

    try:
        available_space = space_info[headers.index('Available')]
    except ValueError:
        print("Error: Could not find 'Available' in the headers.")
        available_space = 'Unknown'

    print(f"Available space on {partition}: {available_space}")
    return available_space

# Check if intermediate upgrades are required
def check_intermediate_upgrades(current_version, target_version):
    """
    This function checks if intermediate upgrades are required based on the current BSP version.
    If intermediate upgrades are needed, it returns a list of intermediate versions.
    If no intermediate upgrades are needed, it returns an empty list.
    """
    global INTERMEDIATE_UPGRADES
    if current_version in INTERMEDIATE_UPGRADES:
        return INTERMEDIATE_UPGRADES[current_version]
    else:
        return []

# Ask user if they want to remove backups based on free space in both / and /backup
def prompt_for_backup_removal(ssh):
    available_space_root = check_available_space(ssh, '/')
    available_space_backup = check_available_space(ssh, '/backup')

    unit_root = available_space_root[-1]
    available_value_root = float(available_space_root[:-1])

    unit_backup = available_space_backup[-1]
    available_value_backup = float(available_space_backup[:-1])

    if unit_backup == 'M' and available_value_backup < 120:
        print(f"Warning: Less than 120MB available in /backup ({available_value_backup}MB).")
        remove_backups = input("Would you like to remove old backups to free space? (yes/no): ").strip().lower()

        if remove_backups == 'yes':
            cleanup_old_files(ssh)
        else:
            print("Proceeding without removing backups.")
    elif unit_root == 'M' and available_value_root < 120:
        print(f"Warning: Less than 120MB available on root ({available_value_root}MB).")
        remove_backups = input("Would you like to remove old backups to free space? (yes/no): ").strip().lower()

        if remove_backups == 'yes':
            cleanup_old_files(ssh)
        else:
            print("Proceeding without removing backups.")
    else:
        print(f"Sufficient space in / ({available_value_root}{unit_root}) and /backup ({available_value_backup}{unit_backup}) available, proceeding.")

# Ensure the remote directory exists
def ensure_remote_directory(sftp, remote_dir):
    try:
        sftp.stat(remote_dir)
        print(f"Directory {remote_dir} already exists on the remote server.")
    except FileNotFoundError:
        print(f"Directory {remote_dir} does not exist. Creating it...")
        sftp.mkdir(remote_dir)

# Upload BSP package to the gateway
def upload_bsp_file(sftp, bsp_file):
    if not os.path.exists(bsp_file):
        raise FileNotFoundError(f"The BSP file '{bsp_file}' does not exist. Please check the path.")

    ensure_remote_directory(sftp, REMOTE_BSP_DIR)

    print("Uploading BSP package...")
    sftp.put(bsp_file, REMOTE_BSP_DIR + os.path.basename(bsp_file))
    print("BSP package uploaded.")

# Unzip BSP package on the gateway and get the list of folders extracted
def unzip_bsp_package(ssh, bsp_file):
    bsp_filename = os.path.basename(bsp_file)
    unzip_command = f'unzip {REMOTE_BSP_DIR}{bsp_filename} -d {REMOTE_BSP_DIR}'
    print(f"Executing: {unzip_command}")
    execute_command(ssh, unzip_command, use_sudo=True)
    time.sleep(5)
    print("BSP package unzipped.")

    # After successful unzipping, remove the ZIP file
    remove_zip_command = f'rm {REMOTE_BSP_DIR}{bsp_filename}'
    print(f"Removing ZIP archive: {remove_zip_command}")
    execute_command(ssh, remove_zip_command, use_sudo=True)
    print(f"ZIP archive {bsp_filename} removed.")

    # List extracted folders (assuming each folder represents a package)
    command = f'ls -d {REMOTE_BSP_DIR}*/'
    folders = execute_command(ssh, command, use_sudo=True).strip().splitlines()
    print(f"Extracted folders: {folders}")
    return folders

# Dynamically create snmpManaged-feed.conf file based on extracted folders
def create_snmp_feed(folders):
    feed_lines = [
        "# Dynamically generated snmpManaged-feed.conf\n",
        "# Added paths to the extracted BSP packages:\n"
    ]

    for folder in folders:
        feed_lines.append(f"src/gz {os.path.basename(folder.rstrip('/'))} file://{folder}\n")

    snmp_feed_content = "".join(feed_lines)
    return snmp_feed_content

# Upload the generated snmpManaged-feed.conf to the gateway
def upload_snmp_feed(ssh, sftp, snmp_feed_content):
    with open('snmpManaged-feed.conf', 'w') as f:
        f.write(snmp_feed_content)

    print("Uploading snmpManaged-feed.conf...")
    sftp.put('snmpManaged-feed.conf', REMOTE_SNMP_CONF_DIR)
    print("snmpManaged-feed.conf uploaded.")

# Clean up space by removing old BSP and backups
def cleanup_old_files(ssh):
    print("Cleaning up old upgrade files and backups...")
    execute_command(ssh, 'rm -rf /lib/firmware/bsp/*', use_sudo=True)
    execute_command(ssh, 'rm -rf /backup/*', use_sudo=True)
    print("Old files and backups cleaned up.")

# Initiate the BSP upgrade
def initiate_bsp_upgrade(ssh, is_admin_user=False):
    print("Initiating BSP upgrade...")

    if is_admin_user:
        # If the user is 'admin', ensure snmpManaged-feed.conf is moved with sudo
        print("Admin user detected, moving snmpManaged-feed.conf with sudo...")
        execute_command(ssh, 'mv snmpManaged-feed.conf /etc/opkg', use_sudo=True)

    # Run opkg update to refresh package paths
    print("Running opkg update...")
    execute_command(ssh, 'opkg update', use_sudo=True)
    time.sleep(5)  # Give some time for the update to complete

    # Initiate BSP upgrade
    print("Initiating tektelic-dist-upgrade...")
    execute_command(ssh, 'tektelic-dist-upgrade -Du', use_sudo=True)
    print("BSP upgrade initiated.")
    time.sleep(15)  # Wait for the upgrade process to start

# Monitor the upgrade process and show live logs
def monitor_upgrade_progress(ssh):
    try:
        # Find the latest log file for the upgrade process
        find_log_command = 'ls -t /var/log/tektelic-dist-upgrade-*.log | head -n 1'
        latest_log_file = execute_command(ssh, find_log_command, use_sudo=True).strip()

        if not latest_log_file:
            print("No upgrade log file found.")
            return

        print(f"Monitoring log file: {latest_log_file}")

        # Start tailing the latest log file to show logs in real-time
        tail_command = f'tail -f {latest_log_file}'
        stdin, stdout, stderr = ssh.exec_command(tail_command)

        while True:
            line = stdout.readline()
            if not line:
                break
            print(line.strip())  # Output the log line by line

            # Check for completion or failure in the log
            if "Upgrade complete" in line:
                print("Upgrade completed successfully.")
                return
            elif "Error" in line or "failed" in line:
                print("Upgrade encountered an error.")
                return

    except Exception as e:
        print(f"Error while monitoring upgrade: {e}")
        time.sleep(10)
        ssh.connect(GATEWAY_IP, username=GATEWAY_USERNAME, password=GATEWAY_PASSWORD)

# Validate the upgrade process
def validate_upgrade(ssh, target_version):
    final_version = check_bsp_version(ssh)
    if final_version == target_version:
        print(f"Upgrade successful! BSP version is now {final_version}")
    else:
        print(f"Upgrade failed! Current BSP version is {final_version}, expected {target_version}")

# Automate the BSP upgrade process
def automate_bsp_upgrade():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(GATEWAY_IP, username=GATEWAY_USERNAME, password=GATEWAY_PASSWORD)

    sftp = ssh.open_sftp()

    current_version = check_bsp_version(ssh)

    prompt_for_backup_removal(ssh)

    intermediate_upgrades = check_intermediate_upgrades(current_version, "5.x.x")

    for version in intermediate_upgrades:
        print(f"Upgrading to intermediate version: {version}")
        upload_bsp_file(sftp, get_bsp_file_for_version(version))
        folders = unzip_bsp_package(ssh, get_bsp_file_for_version(version))

        snmp_feed_content = create_snmp_feed(folders)
        upload_snmp_feed(ssh, sftp, snmp_feed_content)

        initiate_bsp_upgrade(ssh)
        monitor_upgrade_progress(ssh)

    upload_bsp_file(sftp, LOCAL_BSP_PATH)
    folders = unzip_bsp_package(ssh, LOCAL_BSP_PATH)

    snmp_feed_content = create_snmp_feed(folders)
    upload_snmp_feed(ssh, sftp, snmp_feed_content)

    initiate_bsp_upgrade(ssh)
    monitor_upgrade_progress(ssh)

    validate_upgrade(ssh, "5.x.x")

    sftp.close()
    ssh.close()

# Run the automation
if __name__ == '__main__':
    automate_bsp_upgrade()

