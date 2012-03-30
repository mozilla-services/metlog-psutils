%define name metlog-psutils
%define pythonname MetlogPsutils
%define version 0.1
%define unmangled_version %{version}
%define release 0

Summary: Process monitoring plugin for metlog
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{pythonname}-%{unmangled_version}.tar.gz
License: MPL
Group: Development/Libraries
BuildRoot: %{_tmppath}/%{pythonname}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildArch: noarch
Vendor: Victor Ng <vng@mozilla.com>
Requires: 
Obsoletes:

Url: https://github.com/mozilla-services/metlog-psutils

%description
================================
Metlog Process monitoring plugin
================================

A plugin for 'Metlog' which provides extensions to monitor a process's memory,
cpu, network and thread utilization.

%prep
%setup -n %{pythonname}-%{unmangled_version} -n %{pythonname}-%{unmangled_version}

%build
python2.6 setup.py build

%install
python2.6 setup.py install --single-version-externally-managed --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES

%defattr(-,root,root)
