<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

This file is converted to a man page using pandoc. The ":   " prefix uses the
pandoc definition list syntax to produce proper option entries in the man output.
-->

# Command *'aspm'*

## General options

**-h**

:   Show a short help message and exit.

**-q**

:   Be quiet (print only important messages like warnings).

**-d**

:   Print debugging information.

**--debug-modules** *MODNAME[,MODNAME1,...]*

:   The '-d' option enables all debug messages. This option limits them to the specified
    modules. For example, '-d --debug-modules MSR' will only show debug messages from the
    'MSR' module.

**--version**

:   Print the version number and exit.

**-H** *HOSTNAME*, **--host** *HOSTNAME*

:   Host name or IP address of the target system. The pepc command will be executed on this system
    using SSH, instead of running it locally. If not specified, the command will be run locally.

**-U** *USERNAME*, **--username** *USERNAME*

:   Name of the user to use for logging into the remote host over SSH. By default, look up the
    user name in SSH configuration files. If not found, use the current user name.

**-K** *PRIVKEY*, **--priv-key** *PRIVKEY*

:   Path to the private SSH key for logging into the remote host. If not specified, keys
    configured for the host in SSH configuration files (e.g. `~/.ssh/config`) are used. If no keys
    are configured there, standard key files (e.g. `~/.ssh/id_rsa`) and the SSH agent are tried.

**-D** *DATASET*, **--dataset** *DATASET*

:   This option is for debugging and testing. It specifies the dataset to use for emulating the host
    for running the command on. The datasets are available in 'pepc' source code repository.

    The argument can be a dataset path or name. If specified by name, the following locations are
    searched for the dataset.

    1. `./tests/emul-data` in the program's directory
    2. `$PEPC_DATA_PATH/tests/emul-data`
    3. `$VIRTUAL_ENV/share/pepc/tests/emul-data`
    4. `$HOME/.local/share/pepc/tests/emul-data`
    5. `/usr/local/share/pepc/tests/emul-data`
    6. `/usr/share/pepc/tests/emul-data`

**--force-color**

:   Force colorized output even if the output stream is not a terminal (adds ANSI escape codes).

**--print-man-path**

:   Print the pepc manual pages directory path and exit. Add this path to the `MANPATH`
    environment variable to make the manual pages available to the 'man' tool.

## Subcommand *'info'*

Retrieve PCI ASPM information for the system.

**--policy**

:   Retrieve the current global PCI ASPM policy from `/sys/module/pcie_aspm/parameters/policy`. The
    "default" policy indicates the system's default.

**--policies**

:   Retrieve the list of available PCI ASPM policies from `/sys/module/pcie_aspm/parameters/policy`.

**--device** *ADDR*

:   Specify the PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'.

**--l1-aspm**

:   Retrieve the L1 ASPM status (on/off) for the PCI device specified by '--device'. Reads from
    `/sys/bus/pci/devices/{device}/link/l1_aspm`.

## Subcommand *'config'*

Configure PCI ASPM settings. If no parameter is provided, the current value(s) will be displayed.

**--policy** *[POLICY]*

:   Set the global PCI ASPM policy by writing to `/sys/module/pcie_aspm/parameters/policy`. Use
    "default" to reset the policy to the system's default setting.

**--device** *ADDR*

:   Specify the PCI device address for the '--l1-aspm' option. Example: '0000:00:02.0'.

**--l1-aspm** *[OPTION]*

:   Enable or disable L1 ASPM for the PCI device specified by '--device'. This is done via
    `/sys/bus/pci/devices/{device}/link/l1_aspm`. Valid values are 'on', 'off', 'enable', 'disable',
    'true', or 'false'.
