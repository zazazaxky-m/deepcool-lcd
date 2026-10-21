Name:           deepcool-lcd
Version:        1.0.0
Release:        1%{?dist}
Summary:        Custom screens for DeepCool LM-series AIO cooler LCDs
License:        MIT AND OFL-1.1 AND Bitstream-Vera
URL:            https://github.com/zazazaxky-m/deepcool-lcd
Source0:        %{url}/archive/refs/tags/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  make
BuildRequires:  systemd-rpm-macros
Requires:       python3 >= 3.9
Requires:       python3dist(pyusb)
Requires:       python3dist(psutil)
Requires:       python3dist(pillow) >= 9.1
Requires:       systemd
Recommends:     python3dist(pygobject)
Recommends:     gtk4
Conflicts:      deepcool-lm

%description
Shows live CPU and GPU temperatures, load, clocks, power and memory on the LCD of
DeepCool LM-series AIO coolers, with 15 layouts, custom colors, adjustable brightness
and refresh rate, pictures and solid colors. Includes DeepCool LCD Studio, a GTK 4 app
to customize the screen. Not affiliated with DeepCool.

%prep
%autosetup -n %{name}-%{version}

%build
# nothing to build

%install
%make_install PREFIX=%{_prefix}

%post
systemd-sysusers %{_sysusersdir}/%{name}.conf || :
udevadm control --reload || :
udevadm trigger --subsystem-match=usb --attr-match=idVendor=3633 --action=add || :
udevadm trigger --subsystem-match=powercap --action=add || :
%systemd_post %{name}.service
if [ "$1" -eq 1 ]; then
    systemctl disable --now deepcool-lm >/dev/null 2>&1 || :
    systemctl enable --now %{name}.service >/dev/null 2>&1 || :
fi

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%license LICENSE data/fonts/OFL-FiraSans.txt data/fonts/LICENSE-Hack.md
%{_docdir}/%{name}/
%{_bindir}/%{name}
%{_bindir}/%{name}-studio
%{_prefix}/lib/%{name}/
%{_datadir}/%{name}/
%{_unitdir}/%{name}.service
%{_udevrulesdir}/60-%{name}.rules
%{_sysusersdir}/%{name}.conf
%{_datadir}/applications/io.github.zazazaxky_m.DeepCoolLCD.desktop
%{_datadir}/metainfo/io.github.zazazaxky_m.DeepCoolLCD.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.zazazaxky_m.DeepCoolLCD.svg

%changelog
* Wed Oct 21 2026 zazazaxky-m <zazazaxky-m@users.noreply.github.com> - 1.0.0-1
- First release
