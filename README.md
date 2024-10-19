# BSP Upgrade Automation Script

## Overview

This Python script automates the process of upgrading the Board Support Package (BSP) on Tektelic Kona Gateways (Enterprise, Micro, Macro, and Mega). It follows the official Tektelic BSP upgrade guide, handling intermediate upgrades, space management, and configuration file adjustments.

## Features

- Automatic detection of current BSP version
- Support for intermediate upgrades when necessary
- Dynamic creation and management of `snmpManaged-feed.conf`
- Cleanup of old BSP files and backups to ensure sufficient space
- Support for both `root` and `admin` user upgrades
- Real-time monitoring of the upgrade process
- Validation of successful upgrades

## Prerequisites

- Python 3.6 or higher
- `paramiko` library for SSH connections
- Access to the Tektelic Gateway via SSH
- BSP upgrade packages for your gateway model

## Installation

1. Clone this repository or download the script:
   ```
   git clone https://github.com/salacoste/tektelic_bsp_universal_update_script.git
   cd tektelic_bsp_universal_update_script
   ```

2. Install the required Python packages:
   ```
   pip install paramiko
   ```

## Configuration

Before running the script, you need to configure it with your gateway details:

1. Open the script in a text editor.
2. Locate the configuration section at the top of the file:
   ```python
   # Configuration details (replace with actual values)
   GATEWAY_IP = 'ip_address'
   GATEWAY_USERNAME = 'root'
   GATEWAY_PASSWORD = ''
   LOCAL_BSP_PATH = '/path/to/your/BSP_package.zip'
   ```
3. Replace these values with your actual gateway IP, username, password, and the path to your BSP upgrade package.

## Usage

To run the script:

```
python bsp_upgrade.py
```

The script will:
1. Connect to your gateway
2. Check the current BSP version
3. Determine if intermediate upgrades are needed
4. Clean up old files if necessary
5. Upload and unzip the BSP package
6. Create and upload the `snmpManaged-feed.conf` file
7. Initiate the upgrade process
8. Monitor the upgrade progress
9. Validate the successful upgrade

## Important Notes

- **Backup**: Always create a backup of your gateway configuration before running this script.
- **Power**: Ensure stable power to the gateway during the upgrade process.
- **Space**: The script will prompt you to remove old backups if space is low.
- **Interruptions**: Do not interrupt the script once it starts the upgrade process.

## Troubleshooting

If you encounter issues:

1. Check the gateway's logs at `/var/log/tektelic-dist-upgrade-*.log`
2. Ensure you have the correct permissions and credentials
3. Verify network connectivity to the gateway
4. Check if the BSP package is compatible with your gateway model

## Contributing

Contributions to improve the script are welcome. Please submit a pull request or open an issue to discuss proposed changes.

## License

[MIT License](LICENSE)

## Disclaimer

This script is provided as-is, without any warranties. Always test in a non-production environment first.

## Contact

For support or questions, please create an issue / PR.

Ivan Dergachev - Sales Engineer - TEKTELIC Comm.







# BSP Upgrade Automation Script

## Overview

This Python script automates the process of upgrading the Board Support Package (BSP) on Tektelic Kona Gateways (Enterprise, Micro, Macro, and Mega). It follows the official Tektelic BSP upgrade guide, handling intermediate upgrades, space management, and configuration file adjustments.

## Features

- Automatic detection of current BSP version
- Support for intermediate upgrades when necessary
- Dynamic creation and management of `snmpManaged-feed.conf`
- Cleanup of old BSP files and backups to ensure sufficient space
- Support for both `root` and `admin` user upgrades
- Real-time monitoring of the upgrade process
- Validation of successful upgrades

## Prerequisites

- Python 3.6 or higher
- `pip` (Python package installer)
- Access to the Tektelic Gateway via SSH
- BSP upgrade packages for your gateway model

## Installation

1. Clone this repository or download the script:
   ```
   git clone https://github.com/yourusername/tektelic-bsp-upgrade.git
   cd tektelic-bsp-upgrade
   ```

2. Create a virtual environment:
   ```
   python3 -m venv venv
   ```

3. Activate the virtual environment:
   - On Windows:
     ```
     venv\Scripts\activate
     ```
   - On macOS and Linux:
     ```
     source venv/bin/activate
     ```

4. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

   Note: If `requirements.txt` doesn't exist, create it with the following content:
   ```
   paramiko==2.7.2
   ```
   Then run the pip install command above.

## Configuration

Before running the script, you need to configure it with your gateway details:

1. Open the script in a text editor.
2. Locate the configuration section at the top of the file:
   ```python
   # Configuration details (replace with actual values)
   GATEWAY_IP = '10.7.7.222'
   GATEWAY_USERNAME = 'root'
   GATEWAY_PASSWORD = ''
   LOCAL_BSP_PATH = '/path/to/your/BSP_package.zip'
   ```
3. Replace these values with your actual gateway IP, username, password, and the path to your BSP upgrade package.

4. Find the `get_bsp_file_for_version` function in the script and update the `bsp_files` dictionary with the correct paths for each BSP version:
   ```python
   def get_bsp_file_for_version(version):
       bsp_files = {
           "1.6.5": "/path/to/BSP_v1.6.5.zip",   # For upgrading from very old versions
           "3.1.5": "/path/to/BSP_v3.1.5.zip",   # Intermediate upgrade before 4.x.x
           "4.0.3": "/path/to/BSP_v4.0.3.zip",   # Upgrade step between v3.x.x and v5.x.x
           "5.x.x": "/path/to/BSP_v5.x.x.zip",   # Final upgrade to BSP v5.x.x or newer
           "7.1.2": "/path/to/BSP_7.1.2.zip"     # Latest version
       }
       # ... rest of the function
   ```

Replace `/path/to/...` with the actual paths to your BSP files for each version. Ensure you have all the necessary BSP files available at the specified paths.


## Usage

To run the script:

1. Ensure your virtual environment is activated (you should see `(venv)` in your command prompt).

2. Run the script:
   ```
   python bsp_upgrade.py
   ```

The script will:
1. Connect to your gateway
2. Check the current BSP version
3. Determine if intermediate upgrades are needed
4. Clean up old files if necessary
5. Upload and unzip the BSP package
6. Create and upload the `snmpManaged-feed.conf` file
7. Initiate the upgrade process
8. Monitor the upgrade progress
9. Validate the successful upgrade

## Important Notes

- **Backup**: Always create a backup of your gateway configuration before running this script.
- **Power**: Ensure stable power to the gateway during the upgrade process.
- **Space**: The script will prompt you to remove old backups if space is low.
- **Interruptions**: Do not interrupt the script once it starts the upgrade process.
- **Virtual Environment**: Always use the virtual environment to ensure consistency in package versions.

## Troubleshooting

If you encounter issues:

1. Check the gateway's logs at `/var/log/tektelic-dist-upgrade-*.log`
2. Ensure you have the correct permissions and credentials
3. Verify network connectivity to the gateway
4. Check if the BSP package is compatible with your gateway model
5. Make sure you're running the script from within the activated virtual environment

## Contributing

Contributions to improve the script are welcome. Please submit a pull request or open an issue to discuss proposed changes.

## License

[MIT License](LICENSE)

## Disclaimer

This script is provided as-is, without any warranties. Always test in a non-production environment first.

## Contact

For support or questions, please create an issue / PR.

Ivan Dergachev - Sales Engineer - TEKTELIC Comm.
