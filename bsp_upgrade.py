#!/usr/bin/env python3

import paramiko
import os
import time
import select
import re
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bsp_upgrade.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration details
GATEWAY_IP = '10.7.7.184'
GATEWAY_USERNAME = 'root'  # Use 'admin' if not root
GATEWAY_PASSWORD = 'your_password'
SUDO_PASSWORD = GATEWAY_PASSWORD  # Use gateway password for sudo
TARGET_BSP_VERSION = "7.1.2"  # Target BSP version to upgrade to
BSP_DIR = '/Users/r2d2/Downloads/'  # Directory with BSP archives
STABILIZATION_WAIT = 60  # Seconds to wait after reboot

# Paths configuration
REMOTE_BSP_DIR = '/lib/firmware/bsp/'
REMOTE_SNMP_CONF_DIR = '/etc/opkg/snmpManaged-feed.conf'

# Direct upgrade paths for each model
DIRECT_UPGRADE_VERSIONS = {
    'Micro': ['4.0.2', '5.1.x', '6.1.x'],
    'Macro': ['5.x.x', '6.1.x'],
    'Mega': ['5.x.x', '6.1.x']
}

# Optimal upgrade paths for each model
OPTIMAL_UPGRADE_PATHS = {
    'Micro': {
        "1.x.x": ["2.1.3", "3.3.7", "4.0.2", "7.x.x"],
        "2.x.x": ["3.3.7", "4.0.2", "7.x.x"],
        "3.x.x": ["4.0.2", "7.x.x"],
        "4.0.2": ["7.x.x"],
        "5.1.x": ["7.x.x"],
        "6.1.x": ["7.x.x"]
    },
    'Macro': {
        "1.x.x": ["2.0.1", "3.1.5", "4.0.3", "5.x.x", "7.x.x"],
        "2.x.x": ["3.1.5", "4.0.3", "5.x.x", "7.x.x"],
        "3.x.x": ["4.0.3", "5.x.x", "7.x.x"],
        "4.x.x": ["5.x.x", "7.x.x"],
        "5.x.x": ["7.x.x"],
        "6.1.x": ["7.x.x"]
    },
    'Mega': {
        "1.x.x": ["2.0.1", "3.1.4", "4.0.3", "5.x.x", "7.x.x"],
        "2.x.x": ["3.1.4", "4.0.3", "5.x.x", "7.x.x"],
        "3.x.x": ["4.0.3", "5.x.x", "7.x.x"],
        "4.x.x": ["5.x.x", "7.x.x"],
        "5.x.x": ["7.x.x"],
        "6.1.x": ["7.x.x"]
    }
}

class SSHConnectionError(Exception):
    """Custom exception for SSH connection issues"""
    pass

class BSPVersionError(Exception):
    """Custom exception for BSP version related issues"""
    pass

class SFTPError(Exception):
    """Custom exception for SFTP related issues"""
    pass

def execute_command(ssh, command, use_sudo=False, timeout=30):
    """Execute command on remote gateway with timeout and sudo support"""
    try:
        if 'tektelic-dist' in command:
            command = f'PATH=$PATH:/usr/sbin {command}'
            
        if use_sudo and GATEWAY_USERNAME != 'root':
            command = f"echo {SUDO_PASSWORD} | sudo -S bash -c '{command}'"
        
        logger.debug(f"Executing command: {command}")
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        
        err = stderr.read().decode()
        out = stdout.read().decode()
        
        if err and not err.startswith('sudo:'):
            logger.error(f"Command error output: {err}")
            raise Exception(f"Command failed: {command}\nError: {err}")
            
        if out:
            logger.debug(f"Command output: {out}")
            
        return out.strip()
    except Exception as e:
        logger.error(f"Error executing command: {command}\nError: {str(e)}")
        raise

def get_sftp_session(ssh):
    """Get new SFTP session"""
    try:
        sftp = ssh.open_sftp()
        logger.info("New SFTP session opened")
        return sftp
    except Exception as e:
        logger.error(f"Error opening SFTP session: {str(e)}")
        raise SFTPError(f"Failed to open SFTP session: {str(e)}")

def verify_ssh_connection(ssh):
    """Verify SSH connection is active"""
    try:
        execute_command(ssh, 'uptime')
        return True
    except:
        return False

def reconnect_ssh(max_attempts=10, delay=30):
    """Attempt to reconnect to SSH with retries"""
    for attempt in range(max_attempts):
        try:
            logger.info(f"Attempting to reconnect (attempt {attempt + 1}/{max_attempts})")
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(GATEWAY_IP, username=GATEWAY_USERNAME, password=GATEWAY_PASSWORD)
            
            if verify_ssh_connection(ssh):
                logger.info("SSH reconnection successful")
                return ssh
            else:
                raise SSHConnectionError("Connection established but not responding")
                
        except Exception as e:
            if attempt == max_attempts - 1:
                raise SSHConnectionError(f"Failed to reconnect after {max_attempts} attempts: {str(e)}")
            logger.warning(f"Reconnection failed, retrying in {delay} seconds: {str(e)}")
            time.sleep(delay)

def check_bsp_version(ssh):
    """Check current BSP version and determine gateway model"""
    try:
        output = execute_command(ssh, 'system_version', use_sudo=(GATEWAY_USERNAME != 'root')).strip()
        logger.info(f"System Version Output:\n{output}")
        
        version = None
        model = None
        upgrade_in_progress = False
        
        for line in output.split('\n'):
            if line.startswith('Description:'):
                for gw_type in ['Micro', 'Macro', 'Mega']:
                    if gw_type in line:
                        model = gw_type
                        break
            elif line.startswith('Release:'):
                version = line.split(':')[1].strip()
                if 'upgrade-in-progress' in version:
                    upgrade_in_progress = True
                    version = version.replace('upgrade-in-progress', '').strip()
        
        if not version or not model:
            raise BSPVersionError("Could not determine gateway version or model")
            
        logger.info(f"Gateway Model: {model}")
        logger.info(f"Current BSP Version: {version}")
        logger.info(f"Upgrade in progress: {upgrade_in_progress}")
        
        return version, model, upgrade_in_progress
    except Exception as e:
        logger.error(f"Error checking BSP version: {str(e)}")
        raise

def get_bsp_file_for_version(version, model):
    """Get BSP file path for specific version"""
    try:
        if version == "7.x.x":
            version = "7.1.2"
            
        bsp_file = os.path.join(BSP_DIR, f"BSP_{version}.zip")
        
        if not os.path.exists(bsp_file):
            raise FileNotFoundError(
                f"BSP file not found: {bsp_file}\n"
                f"Please ensure you have BSP_{version}.zip in {BSP_DIR}"
            )
        
        file_size = os.path.getsize(bsp_file) / (1024 * 1024)  # Size in MB
        logger.info(f"Found BSP package: {bsp_file} (Size: {file_size:.2f}MB)")
        return bsp_file
        
    except Exception as e:
        logger.error(f"Error getting BSP file for version {version}: {str(e)}")
        raise

def check_available_space(ssh, partition='/'):
    """Check available space on specified partition"""
    try:
        output = execute_command(ssh, f'df -h {partition}', use_sudo=True)
        lines = output.strip().split('\n')
        if len(lines) < 2:
            raise ValueError("Unexpected df output format")
            
        fields = lines[1].split()
        available = fields[3]
        
        # Convert to MB for comparison
        size = float(available[:-1])
        unit = available[-1].upper()
        if unit == 'G':
            size *= 1024
        elif unit == 'K':
            size /= 1024
            
        return size
    except Exception as e:
        logger.error(f"Error checking available space: {str(e)}")
        raise

def cleanup_old_files(ssh):
    """Clean up old BSP files and backups to free space"""
    try:
        logger.info("Cleaning up old upgrade files and backups...")
        execute_command(ssh, 'rm -rf /lib/firmware/bsp/*', use_sudo=True)
        execute_command(ssh, 'rm -rf /backup/*', use_sudo=True)
        execute_command(ssh, 'rm -f /var/log/tektelic-dist-upgrade-*.log', use_sudo=True)
        execute_command(ssh, 'rm -rf /tmp/bsp_*', use_sudo=True)
        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        raise

def get_extracted_folders(ssh):
    """Get list of folders from extracted BSP package"""
    try:
        folders = execute_command(ssh, f'ls -d {REMOTE_BSP_DIR}*/', use_sudo=True)
        return [folder.strip() for folder in folders.split('\n') if folder.strip()]
    except Exception as e:
        logger.error(f"Error getting extracted folders: {str(e)}")
        raise

def create_snmp_feed(ssh):
    """Create or overwrite snmpManaged-feed.conf using paths from extracted BSP folders"""
    try:
        logger.info("Creating/Updating snmpManaged-feed.conf...")
        
        folders = get_extracted_folders(ssh)
        if not folders:
            raise Exception("No folders found in BSP directory")
        
        logger.info(f"Found folders: {folders}")
        
        feed_lines = [
            "# This file is auto-generated by BSP upgrade script",
            "# Please do not edit manually",
            f"# Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        ]
        
        for folder in folders:
            folder = folder.rstrip('/')
            folder_name = os.path.basename(folder)
            feed_line = f"src/gz {folder_name} file://{folder}"
            feed_lines.append(feed_line)
            
        feed_content = '\n'.join(feed_lines) + '\n'
        logger.info(f"Generated feed content:\n{feed_content}")
        
        execute_command(ssh, 'mkdir -p /etc/opkg', use_sudo=True)
        temp_feed_file = '/tmp/snmpManaged-feed.conf.tmp'
        
        echo_cmd = f"echo '{feed_content}' > {temp_feed_file}"
        execute_command(ssh, echo_cmd, use_sudo=True)
        
        execute_command(ssh, f'mv {temp_feed_file} {REMOTE_SNMP_CONF_DIR}', use_sudo=True)
        execute_command(ssh, f'chmod 644 {REMOTE_SNMP_CONF_DIR}', use_sudo=True)
        
        # Verify content
        actual_content = execute_command(ssh, f'cat {REMOTE_SNMP_CONF_DIR}', use_sudo=True)
        if feed_content.strip() != actual_content.strip():
            raise Exception("Feed file content verification failed")
        
        logger.info("snmpManaged-feed.conf updated and verified successfully")
        
    except Exception as e:
        logger.error(f"Error updating snmpManaged-feed.conf: {str(e)}")
        raise

def verify_feed_file(ssh, expected_folders):
    """Verify feed file contains all required folders"""
    try:
        feed_content = execute_command(ssh, f'cat {REMOTE_SNMP_CONF_DIR}', use_sudo=True)
        
        feed_folders = [line.split('file://')[1].strip() 
                       for line in feed_content.splitlines() 
                       if line.strip() and not line.startswith('#') and 'file://' in line]
        
        expected_folders = [folder.rstrip('/') for folder in expected_folders]
        
        logger.info("Feed file verification:")
        logger.info(f"Expected folders: {expected_folders}")
        logger.info(f"Found in feed: {feed_folders}")
        
        missing_folders = []
        for folder in expected_folders:
            if not any(folder.rstrip('/') == f.rstrip('/') for f in feed_folders):
                missing_folders.append(folder)
        
        if missing_folders:
            raise Exception(f"Missing folders in feed file: {missing_folders}")
            
        logger.info("Feed file verification passed")
        return True
        
    except Exception as e:
        logger.error(f"Feed file verification failed: {str(e)}")
        raise

def upload_and_prepare_bsp(ssh, sftp, bsp_file):
    """Upload BSP file and prepare for upgrade"""
    try:
        # Verify SFTP session is active
        try:
            sftp.listdir('/')
        except:
            logger.warning("SFTP session not active, getting new session")
            sftp = get_sftp_session(ssh)

        execute_command(ssh, f'mkdir -p {REMOTE_BSP_DIR}', use_sudo=True)
        
        # Verify space before upload
        file_size = os.path.getsize(bsp_file) / (1024 * 1024)
        required_space = file_size * 1.5
        
        logger.info(f"Checking space requirements. Need {required_space:.2f}MB")
        available_space = check_available_space(ssh)
        logger.info(f"Initially available space: {available_space:.2f}MB")
        
        if available_space < required_space:
            if not check_and_ensure_space(ssh, required_space, auto_cleanup=True):
                raise Exception(f"Cannot proceed: insufficient space after cleanup. Need {required_space:.2f}MB")
        
        # Upload file
        remote_file = os.path.join(REMOTE_BSP_DIR, os.path.basename(bsp_file))
        logger.info(f"Uploading BSP file to {remote_file}")
        try:
            sftp.put(bsp_file, remote_file)
        except Exception as e:
            raise Exception(f"Failed to upload BSP file: {str(e)}")
        
        # Verify upload
        try:
            remote_size = int(execute_command(ssh, f'stat -c%s "{remote_file}"', use_sudo=True))
            local_size = os.path.getsize(bsp_file)
            if remote_size != local_size:
                raise Exception(f"Size mismatch after upload: local={local_size}, remote={remote_size}")
        except Exception as e:
            logger.error(f"Upload verification failed: {str(e)}")
            raise
        
        # Extract BSP
        logger.info("Unzipping BSP package...")
        try:
            unzip_cmd = f'cd {REMOTE_BSP_DIR} && busybox unzip -o {os.path.basename(bsp_file)}'
            execute_command(ssh, unzip_cmd, use_sudo=True)
        except Exception as e:
            logger.warning(f"busybox unzip failed: {e}, trying standard unzip")
            try:
                unzip_cmd = f'cd {REMOTE_BSP_DIR} && unzip -o {os.path.basename(bsp_file)}'
                execute_command(ssh, unzip_cmd, use_sudo=True)
            except Exception as e2:
                raise Exception(f"Both unzip attempts failed: {str(e2)}")
        
        # Verify extraction
        extracted_folders = get_extracted_folders(ssh)
        if not extracted_folders:
            raise Exception("No folders found after extraction")
        logger.info(f"Extracted folders: {extracted_folders}")
        
        # Remove zip file
        try:
            execute_command(ssh, f'rm {remote_file}', use_sudo=True)
        except Exception as e:
            logger.warning(f"Failed to remove zip file: {str(e)}")
        
        # Create and verify feed file
        create_snmp_feed(ssh)
        verify_feed_file(ssh, extracted_folders)
        
        logger.info("BSP package prepared successfully")
        
    except Exception as e:
        logger.error(f"Error preparing BSP package: {str(e)}")
        try:
            execute_command(ssh, f'rm -rf {REMOTE_BSP_DIR}/*', use_sudo=True)
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup after error: {str(cleanup_error)}")
        raise

def initiate_bsp_upgrade(ssh):
    """Initiate the BSP upgrade process"""
    try:
        logger.info("Initiating BSP upgrade...")
        
        # Verify system state before upgrade
        version, model, upgrade_in_progress = check_bsp_version(ssh)
        if upgrade_in_progress:
            raise Exception("System is already in upgrade state")
        
        # Update package manager
        logger.info("Updating package manager...")
        execute_command(ssh, 'opkg update', use_sudo=True)
        time.sleep(5)
        
        logger.info("Starting tektelic-dist-upgrade...")
        upgrade_command = 'PATH=$PATH:/usr/sbin tektelic-dist-upgrade -Ddu'
        execute_command(ssh, upgrade_command, use_sudo=True)
        
        time.sleep(5)
        _, _, upgrade_started = check_bsp_version(ssh)
        if not upgrade_started:
            raise Exception("Upgrade did not start properly")
            
        logger.info("BSP upgrade initiated successfully")
        
    except Exception as e:
        logger.error(f"Error initiating upgrade: {str(e)}")
        raise
def check_and_ensure_space(ssh, required_space, auto_cleanup=True):
    """
    Check if there's enough space and attempt to free up space if needed
    Returns: bool indicating if enough space is available after cleanup
    """
    try:
        logger.info(f"Checking space requirements. Need {required_space:.2f}MB")
        
        # Check initial space
        available_space = check_available_space(ssh)
        logger.info(f"Initially available space: {available_space:.2f}MB")
        
        if available_space >= required_space:
            return True
            
        if not auto_cleanup:
            logger.warning(f"Insufficient space: {available_space:.2f}MB available, {required_space:.2f}MB required")
            cleanup = input("Would you like to clean up old files to free space? (yes/no): ").lower()
            if cleanup != 'yes':
                return False
        
        # Try cleaning steps one by one and check space after each
        cleanup_steps = [
            {
                'name': 'Old BSP files',
                'command': 'rm -rf /lib/firmware/bsp/*',
                'expected_gain': 50
            },
            {
                'name': 'Old backups',
                'command': 'rm -rf /backup/*',
                'expected_gain': 100
            },
            {
                'name': 'Log files',
                'command': 'rm -f /var/log/tektelic-dist-upgrade-*.log',
                'expected_gain': 10
            },
            {
                'name': 'Temporary files',
                'command': 'rm -rf /tmp/bsp_*',
                'expected_gain': 5
            }
        ]
        
        for step in cleanup_steps:
            logger.info(f"Attempting to clean {step['name']}...")
            try:
                execute_command(ssh, step['command'], use_sudo=True)
                available_space = check_available_space(ssh)
                logger.info(f"Available space after cleaning {step['name']}: {available_space:.2f}MB")
                
                if available_space >= required_space:
                    logger.info("Sufficient space now available")
                    return True
            except Exception as e:
                logger.warning(f"Failed to clean {step['name']}: {str(e)}")
        
        # Final space check
        available_space = check_available_space(ssh)
        if available_space >= required_space:
            return True
            
        logger.error(f"Could not free up enough space. Available: {available_space:.2f}MB, Required: {required_space:.2f}MB")
        return False
        
    except Exception as e:
        logger.error(f"Error during space management: {str(e)}")
        raise

def print_upgrade_plan(current_version, model, upgrade_path, estimated_time, space_required):
    """Print detailed upgrade plan"""
    version_in_progress = current_version  # Локальная копия для отслеживания версий
    
    print("\n" + "="*50)
    print("BSP UPGRADE PLAN")
    print("="*50)
    print(f"Gateway Model: {model}")
    print(f"Current Version: {current_version}")
    print(f"Target Version: {TARGET_BSP_VERSION}")
    print("\nUpgrade Path:")
    for i, version in enumerate(upgrade_path, 1):
        print(f"  {i}. {version_in_progress} → {version}")
        version_in_progress = version
    print(f"\nEstimated Time: {estimated_time} minutes")
    print(f"Required Free Space: {space_required} MB")
    print("="*50)
    
    proceed = input("\nDo you want to proceed with the upgrade? (yes/no): ").lower()
    return proceed == 'yes'

def monitor_upgrade_progress(ssh, timeout=1800, check_interval=1):
    """Monitor the upgrade process and show progress"""
    start_time = time.time()
    upgrade_completed = False
    last_progress = 0
    upgrade_started = False
    reboot_detected = False
    reboot_count = 0
    MAX_REBOOTS = 3
    last_activity = time.time()
    MAX_INACTIVITY = 300  # 5 minutes
    
    try:
        # Wait for upgrade to start
        for _ in range(30):
            try:
                _, _, in_progress = check_bsp_version(ssh)
                if in_progress:
                    upgrade_started = True
                    break
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Error checking BSP version during startup: {str(e)}")
                time.sleep(1)
        
        if not upgrade_started:
            raise Exception("Upgrade did not start within 30 seconds")
        
        while time.time() - start_time < timeout:
            try:
                current_time = time.time()
                
                if current_time - last_activity > MAX_INACTIVITY:
                    raise Exception(f"No activity detected for {MAX_INACTIVITY} seconds")
                
                # Check system version
                try:
                    version_output = execute_command(ssh, 'system_version', use_sudo=True)
                    last_activity = current_time
                    
                    if 'upgrade-in-progress' in version_output:
                        logger.info("Upgrade is in progress...")
                    elif upgrade_started:
                        logger.info("System appears to have completed upgrade")
                        upgrade_completed = True
                        break
                    
                except Exception as e:
                    if upgrade_started and not reboot_detected:
                        logger.info("Lost connection - system might be rebooting...")
                        reboot_detected = True
                        reboot_count += 1
                        if reboot_count > MAX_REBOOTS:
                            raise Exception(f"Too many reboots detected ({reboot_count})")
                    
                    time.sleep(30)
                    try:
                        ssh = reconnect_ssh()
                        if reboot_detected:
                            logger.info("Successfully reconnected after reboot")
                            reboot_detected = False
                            last_activity = time.time()
                    except Exception as reconnect_error:
                        logger.error(f"Failed to reconnect: {str(reconnect_error)}")
                        continue
                
                # Check progress
                try:
                    progress_output = execute_command(ssh, 'dmesg | grep "BSP upgrade progress:" | tail -n 1', use_sudo=True)
                    if progress_output:
                        progress = int(progress_output.split("progress: ")[1])
                        if progress != last_progress:
                            last_progress = progress
                            last_activity = current_time
                            logger.info(f"Upgrade progress: {progress}%")
                            print(f'\rProgress: {progress}%', end='', flush=True)
                except Exception as progress_error:
                    logger.debug(f"Error checking progress: {str(progress_error)}")
                
                time.sleep(check_interval)
                
            except Exception as loop_error:
                logger.error(f"Error in monitoring loop: {str(loop_error)}")
                if "Too many reboots detected" in str(loop_error):
                    raise
                continue

        if not upgrade_completed:
            raise TimeoutError("Upgrade process timed out")
            
        logger.info(f"Waiting {STABILIZATION_WAIT} seconds for system to stabilize...")
        time.sleep(STABILIZATION_WAIT)
        
        print("\nUpgrade process completed!")
            
    except Exception as e:
        logger.error(f"Error monitoring upgrade: {str(e)}")
        raise

def analyze_upgrade_path(current_version, model):
    """Analyze and determine the optimal upgrade path"""
    logger.info(f"Analyzing upgrade path for {model} gateway from version {current_version} to {TARGET_BSP_VERSION}")
    
    base_version = f"{current_version.split('.')[0]}.x.x"
    logger.info(f"Base version for upgrade path: {base_version}")
    
    if any(current_version.startswith(ver.split('.')[0]) for ver in DIRECT_UPGRADE_VERSIONS[model]):
        upgrade_path = [TARGET_BSP_VERSION]
        logger.info("Direct upgrade is possible!")
        estimated_time = 20
        space_required = 40
    else:
        upgrade_path = OPTIMAL_UPGRADE_PATHS[model].get(base_version)
        if not upgrade_path:
            raise ValueError(f"No upgrade path found for {model} gateway version {current_version}")
        estimated_time = 20 * len(upgrade_path)
        space_required = 40 * 2

    logger.info(f"Upgrade path: {' -> '.join(upgrade_path)}")
    logger.info(f"Estimated time: {estimated_time} minutes")
    logger.info(f"Required space: {space_required} MB")
    
    return upgrade_path, estimated_time, space_required

def verify_upgrade_path(upgrade_path, model):
    """Verify all required BSP files exist"""
    missing_files = []
    for version in upgrade_path:
        try:
            get_bsp_file_for_version(version, model)
        except FileNotFoundError as e:
            missing_files.append(version)
    
    if missing_files:
        raise ValueError(f"Missing BSP files for versions: {', '.join(missing_files)}")

def main():
    """Main function to orchestrate the upgrade process"""
    ssh = None
    sftp = None
    
    try:
        logger.info(f"Connecting to gateway {GATEWAY_IP}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(GATEWAY_IP, username=GATEWAY_USERNAME, password=GATEWAY_PASSWORD)
        
        current_version, model, upgrade_in_progress = check_bsp_version(ssh)
        if upgrade_in_progress:
            raise Exception("Gateway is currently in upgrade state. Please wait for it to complete.")
        
        upgrade_path, estimated_time, space_required = analyze_upgrade_path(current_version, model)
        verify_upgrade_path(upgrade_path, model)
        
        if not print_upgrade_plan(current_version, model, upgrade_path, estimated_time, space_required):
            logger.info("Upgrade cancelled by user")
            return

        logger.info("Cleaning up BSP directory...")
        execute_command(ssh, f'rm -rf {REMOTE_BSP_DIR}', use_sudo=True)
        execute_command(ssh, f'mkdir -p {REMOTE_BSP_DIR}', use_sudo=True)
        
        for version in upgrade_path:
            logger.info(f"Starting upgrade to version {version}")
            
            if sftp:
                sftp.close()
            sftp = get_sftp_session(ssh)
            
            try:
                bsp_file = get_bsp_file_for_version(version, model)
                upload_and_prepare_bsp(ssh, sftp, bsp_file)
                initiate_bsp_upgrade(ssh)
                monitor_upgrade_progress(ssh)
                
                sftp.close()
                sftp = None
                
                ssh = reconnect_ssh()
                logger.info("Waiting for system to stabilize...")
                time.sleep(STABILIZATION_WAIT)
                
            except Exception as e:
                logger.error(f"Error during upgrade to version {version}: {str(e)}")
                raise
            finally:
                if sftp:
                    sftp.close()
                if ssh:
                    ssh.close()
        
        final_version, _, _ = check_bsp_version(ssh)
        if final_version == TARGET_BSP_VERSION:
            logger.info(f"Upgrade successful! Final BSP version is {final_version}")
        else:
            raise Exception(f"Upgrade failed! Final version is {final_version}, expected {TARGET_BSP_VERSION}")
        
    except Exception as e:
        logger.error(f"Upgrade process failed: {str(e)}")
        raise
    finally:
        if sftp:
            try:
                sftp.close()
            except Exception as e:
                logger.error(f"Error closing SFTP connection: {str(e)}")
        
        if ssh:
            try:
                ssh.close()
            except Exception as e:
                logger.error(f"Error closing SSH connection: {str(e)}")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"Script execution failed: {str(e)}")
        exit(1)
