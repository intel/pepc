%bcond_without tests

Name:		pepc
Version:	1.6.24
Release:	1%{?dist}
Summary:	Power, Energy, and Performance Configuration tool

License:	BSD-3-Clause
Url:		https://github.com/intel/pepc
Source0:	%url/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:	noarch

BuildRequires:	python3-devel
%if %{with tests}
BuildRequires:	python3-pytest
%endif
Requires:	python3-pepc

%description
Pepc, short for "Power, Energy, and Performance Configurator", is a command-line tool designed for
reading and changing power management features. For example, pepc can be used to modify CPU
or uncore frequency limits for all or a subset of CPUs, cores, modules, dies, or packages in the
system.

%package -n python3-%{name}
Summary:	Pepc Python libraries
BuildRequires:	python3-pyyaml
BuildRequires:	python3-paramiko
Requires:	pepc

%description -n python3-%{name}
Pepc Python libraries

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build

%install
%py3_install
mkdir -p %{buildroot}/%{_mandir}/man1/pepc
install -pDm644 docs/man1/*.1 %{buildroot}/%{_mandir}/man1/pepc

%check
%if %{with tests}
%pytest
%endif

%files
%doc README.md
%license LICENSE.md
%{_bindir}/pepc
%{_mandir}/man1/pepc/pepc-*.1

%files -n python3-%{name}
%{python3_sitelib}/pepclibs
%{python3_sitelib}/pepctools
%{python3_sitelib}/pepc-*.egg-info/

# Date format: date "+%a %b %d %Y"
%changelog
* Thu Mar 16 2023 Niklas Neronin <niklas.neronin@linux.intel.com> - 1.4.6
- Update man pages.

* Fri Jun 24 2022 Artem Bityutskiy <artem.bityutskiy@linux.intel.com> - 1.3.9-1
- Add RPM packaging support.

* Tue Jun 21 2022 Ali Erdinc Koroglu <ali.erdinc.koroglu@intel.com> - 1.3.8-1
- Initial package.
