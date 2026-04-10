<!--
-*- coding: utf-8 -*-
vim: ts=4 sw=4 tw=100 et ai si

This file is converted to a man page using pandoc. The ":   " prefix uses the
pandoc definition list syntax to produce proper option entries in the man output.
-->

# Command *'tpmi'*

## Background

TPMI, or Topology Aware Register and PM Capsule Interface, is a memory-mapped interface for
accessing processor registers related to power management on Intel CPUs.

These registers are exposed via PCIe VSEC (Vendor-Specific Extended Capabilities) and grouped into
TPMI features. For instance, the "ufs" feature includes registers for uncore frequency scaling,
the "rapl" feature covers Running Average Power Limit (RAPL) registers, and the "sst" feature
includes registers for Intel Speed Select Technology (SST).

To decode TPMI features, the 'pepc' tool requires a spec file describing register names, bits, and
offsets in the PCIe memory-mapped address space. Features without a spec file cannot be decoded.

The 'pepc' project includes spec files for some, but not all TPMI features. Spec files for other
features can be requested from Intel Corporation via customer support channels.

The spec files are searched in the following locations and order:

1. `./tpmi`, in the directory of the running program
2. `$PEPC_TPMI_DATA_PATH/tpmi`
3. `$HOME/.local/share/pepc/tpmi`
4. `$VIRTUAL_ENV/share/pepc/tpmi`
5. `/usr/local/share/pepc/tpmi`
6. `/usr/share/pepc/tpmi`

The `PEPC_TPMI_DATA_PATH` provides a mechanism for replacing or extending the standard spec files.
Just set it to a directory with spec files to have 'pepc' use them.

Spec files are YAML files, but they are generated from Intel proprietary XML files using the 'tpmi-
spec-files-generator' tool available in the 'pepc' source code repository.

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

:   Path to the private SSH key for logging into the remote host. Defaults to keys in standard paths
    like `$HOME/.ssh`.

**-D** *DATASET*, **--dataset** *DATASET*

:   This option is for debugging and testing. It specifies the dataset to use for emulating the host
    for running the command on. The datasets are available in 'pepc' source code repository.

    The argument can be a dataset path or name. If specified by name, the following locations are
    searched for the dataset.

    1. `./tests/emul-data` in the program's directory
    2. `$PEPC_DATA_PATH/tests/emul-data`
    3. `$HOME/.local/share/pepc/tests/emul-data`
    4. `$VIRTUAL_ENV/share/tests/emul-data`
    5. `/usr/local/share/pepc/tests/emul-data`
    6. `/usr/share/pepc/tests/emul-data`

**--force-color**

:   Force colorized output even if the output stream is not a terminal (adds ANSI escape codes).

**--print-man-path**

:   Print the pepc manual pages directory path and exit. Add this path to the `MANPATH`
    environment variable to make the manual pages available to the 'man' tool.

## Subcommand *'ls'*

Display supported TPMI features.

**-B** *BASE*, **--base** *BASE*

:   Path to a copy of the TPMI debugfs contents. By default, pepc uses 'Granite Rapids Xeon' and
    searches for `tpmi-<PCI address>` subdirectories within it. This option replaces the default
    'Granite Rapids Xeon' directory with a custom path. Intended for decoding TPMI debugfs dumps
    captured from a different system.

**--vfm** *VFM*

:   VFM (Vendor, Family, Model) identifier of the target CPU as an integer or in
    '[Vendor:]Family:Model' format. Use this option with '--base' when decoding a TPMI debugfs dump
    to identify the CPU model of the system the dump was captured from.

**--list-specs**

:   Display information about TPMI spec files for the target system and exit. Show the detected CPU
    model and available spec files for that model. Spec directories may contain files for different
    CPU models. Select files matching the target system. Note that the target system may not support
    all TPMI features described in the spec files.

**-t**, **--topology**

:   Display TPMI topology (PCI addresses, instance numbers, etc.).

**--unimplemented**

:   Include unimplemented TPMI instances. Unimplemented instances have version number 0xFF and
    represent "empty slots" in the instances table of a TPMI feature. For example, instance 0 may
    be implemented, instance 1 may be unimplemented (version 0xFF), and instance 2 may be
    implemented. By default, unimplemented instances are not shown in the output.

**-F** *FEATURES*, **--features** *FEATURES*

:   Comma-separated list of TPMI feature names to include in the output. Defaults to all supported
    features.

Read one or more TPMI registers.

**-B** *BASE*, **--base** *BASE*

:   Path to a copy of the TPMI debugfs contents. By default, pepc uses 'Granite Rapids Xeon' and
    searches for `tpmi-<PCI address>` subdirectories within it. This option replaces the default
    'Granite Rapids Xeon' directory with a custom path. Intended for decoding TPMI debugfs dumps
    captured from a different system.

**--vfm** *VFM*

:   VFM (Vendor, Family, Model) identifier of the target CPU as an integer or in
    '[Vendor:]Family:Model' format. Use this option with '--base' when decoding a TPMI debugfs dump
    to identify the CPU model of the system the dump was captured from.

**-F** *FEATURES*, **--features** *FEATURES*

:   Comma-separated list of TPMI feature names to read the registers for. Defaults to all supported
    features.

**-a** *ADDRS*, **--addresses** *ADDRS*

:   Comma-separated list of TPMI device PCI addresses to read the registers from. Defaults to all
    devices.

**--packages** *PACKAGES*

:   Comma-separated list of package numbers to read TPMI registers for (defaults to all packages).

**-i** *INSTANCES*, **--instances** *INSTANCES*

:   Comma-separated list of TPMI instance numbers to read registers from (defaults to all
    instances).

**-c** *CLUSTERS*, **--clusters** *CLUSTERS*

:   Comma-separated list of cluster numbers to read registers from (defaults to all clusters). This
    option is only relevant for the 'ufs' TPMI feature, because there may be multiple copies of UFS
    control registers within a TPMI instance, and the copies are referred to as clusters. All other
    TPMI features have only one cluster - cluster 0.

**-R** *REGISTERS*, **--registers** *REGISTERS*

:   Comma-separated list of TPMI register names to read. Defaults to all registers.

**-b** *BITFIELDS*, **--bitfields** *BITFIELDS*

:   Comma-separated list of TPMI register bit field names to decode. Defaults to decoding all bit
    fields.

**-n**, **--no-bitfields**

:   Do not decode and display TPMI register bit field values. When this option is specified, only
    register values will be displayed without decoding the individual bit fields within them.

**--yaml**

:   Display information in YAML format.

## Subcommand *'write'*

Write a value to a TPMI register or its bit field.

**-B** *BASE*, **--base** *BASE*

:   Path to a copy of the TPMI debugfs contents. By default, pepc uses 'Granite Rapids Xeon' and
    searches for `tpmi-<PCI address>` subdirectories within it. This option replaces the default
    'Granite Rapids Xeon' directory with a custom path. Intended for decoding TPMI debugfs dumps
    captured from a different system.

**--vfm** *VFM*

:   VFM (Vendor, Family, Model) identifier of the target CPU as an integer or in
    '[Vendor:]Family:Model' format. Use this option with '--base' when decoding a TPMI debugfs dump
    to identify the CPU model of the system the dump was captured from.

**-F** *FEATURE*, **--feature** *FEATURE*

:   Name of the TPMI feature the register belongs to.

**-a** *ADDRS*, **--addresses** *ADDRS*

:   Comma-separated list of PCI addresses of TPMI devices to write to.

**--packages** *PACKAGES*

:   Comma-separated list of package numbers to write to (defaults to all packages).

**-i** *INSTANCES*, **--instances** *INSTANCES*

:   Comma-separated list of TPMI instance numbers to write to. Defaults to all instances.

**-c** *CLUSTERS*, **--clusters** *CLUSTERS*

:   Comma-separated list of cluster numbers to write to (defaults to all clusters). This option is
    only relevant for the 'ufs' TPMI feature, because there may be multiple copies of UFS control
    registers within a TPMI instance, and the copies are referred to as clusters. All other TPMI
    features have only one cluster - cluster 0.

**-R** *REGNAME*, **--register** *REGNAME*

:   Name of the TPMI register to write.

**-b** *BITFIELD*, **--bitfield** *BITFIELD*

:   Name of the TPMI register bit field to write to. If this option is not specified, the value will
    be written to the entire register. When specified, only the specified bit field within the
    register will be modified.

**-V** *VALUE*, **--value** *VALUE*

:   Value to write to the TPMI register or bit field.
