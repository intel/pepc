#!/bin/sh -euf
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

# A scrappy script to install pepc into a python virtual environment.

PROG="${0##*/}"
PEPC_GIT_URL="git+https://github.com/intel/pepc.git@release"

show_usage()
{
    cat <<EOF
Usage: $PROG [options]

Options:
    -o, --install-path PATH
        The installation path. Default is '\$HOME/.pmtools'.
    --os-name NAME
        The operating system name. Supported values are: ubuntu, debian, fedora, centos, rhel.
        If specified, the script will install OS package dependencies, otherwise it will skip
        this step (not recommended).
    -s, --src-path PATH
        The path to the pepc source code. If not specified, pepc will be installed from pepc
        public repository.
    --shell-rc-path PATH
        The shell rc file to write pepc environment settings to. Default is '\$HOME/.bashrc'.
    -h, --help
EOF
}

fail_usage()
{
    [ -z "$1" ] || printf "%s\n" "$1"
    show_usage
    exit 1
}

# These variables will be set from command line arguments.
install_path="$HOME/.pmtools"
osname=
src_path=
shell_rc_path="$HOME/.bashrc"

# Parse command line arguments.
TEMP=`getopt -n $PROG -o o:,s:,h --long install-path:,os-name:,src-path:,shell-rc-path:,help -- "$@"` || fail_usage ""
eval set -- "$TEMP"

while true; do
        case "$1" in
        -o|--install-path)
                install_path="$2"
                shift
                ;;
        --os-name)
                osname="$2"
                shift
                ;;
        -s|--src-path)
                src_path="$2"
                shift
                ;;
        --shell-rc-path)
                shell_rc_path="$2"
                shift
                ;;
        -h|--help)
                show_usage
                exit 0
                ;;
        --) shift; break
                ;;
        *) fail_usage "Unrecognized option: $1"
                ;;
        esac
        shift
done

# Install OS package dependencies.
if [ -n "$osname" ]; then
    if [ "$osname" = "ubuntu" ] || [ "$osname" = "debian" ]; then
        sudo apt install -y rsync util-linux procps git python3-venv
    elif [ "$osname" = "fedora" ] || [ "$osname" = "centos" ] || [ "$osname" = "rhel" ]; then
        sudo dnf install -y rsync util-linux procps-ng git python3-pip
    else
        echo "Error: Unrecognized OS name '$osname'. Supported OS names are: ubuntu, debian, fedora, centos, rhel." 1>&2
        exit 1
    fi
else
    echo "Warning: OS name not specified. Skipping installation of OS package dependencies." 1>&2
fi

mkdir -p "$install_path"

echo "Creating a python virtual environment"
python3 -m venv "$install_path"

if [ -n "${src_path:-}" ]; then
    echo "Installing pepc into the virtual environment from sources: $src_path"
    "$install_path/bin/pip3" install --upgrade "$src_path"
else
    echo "Installing pepc into the virtual environment from git URL: $PEPC_GIT_URL"
    "$install_path/bin/pip3" install --upgrade "$PEPC_GIT_URL"
fi

cat >> "$shell_rc_path" <<EOF

# === pepc settings ===
VENV='$install_path'
VENV_BIN="\$VENV/bin"

# Ensure the virtual environment's bin directory is in the PATH.
export PATH="\$PATH:\$VENV_BIN"

# Convenience alias for running pepc with sudo.
alias pepc="sudo PATH=\$PATH VIRTUAL_ENV=\$VENV \$VENV_BIN/pepc"

# Enable tab completion for pepc.
eval "\$(\$VENV_BIN/register-python-argcomplete pepc)"

# Enable man pages.
export MANPATH="\$MANPATH:\$(\$VENV_BIN/pepc --print-man-path)"
# === end of pepc settings ===
EOF

echo "pepc installation is complete"
echo "Remember to source your shell rc file or open a new terminal to use pepc:"
echo ". $shell_rc_path"
