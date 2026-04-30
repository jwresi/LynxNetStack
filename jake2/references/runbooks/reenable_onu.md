# Savoy ONU Re-Enable Quick Commands

Use these commands to bring back ONUs that were disabled during the Savoy rogue DHCP/private-LAN isolation work on April 2, 2026.

Credentials:

```text
user: admin
password: <current OLT password from private env or vault>
```

## Generic Re-Enable Flow

```text
telnet <OLT_IP>
enable
configure
interface gpon <PON_PATH>
ont activate <ONU_ID>
exit
exit
show ont info gpon <PON_PATH>
```

If the ONU comes back cleanly and you want the change to persist across OLT reboot:

```text
copy running-config startup-config
```

## OLT01 ONT 4

Reason disabled:

- Private LAN leak source `30:68:93:C1:C5:CD`
- Seen as `192.168.88.1`
- Physical location: `000002.OLT01` `Gpon1/0/2` `ONT 4`
- Serial: `TPLG-31A11BB2`

Commands:

```text
telnet 192.168.55.98
enable
configure
interface gpon 1/0/2
ont activate 4
exit
exit
show mac address-table address 30:68:93:c1:c5:cd
show ont info gpon 1/0/2
```

## OLT05 ONT 4

Reason disabled:

- Rogue DHCP source `D8:44:89:A7:05:C8`
- Was seen as `192.168.88.1`
- Physical location: `000002.OLT05` `Gpon1/0/1` `ONT 4`

Commands:

```text
telnet 192.168.55.95
enable
configure
interface gpon 1/0/1
ont activate 4
exit
exit
show mac address-table address d8:44:89:a7:05:c8
show ont info gpon 1/0/1
```

## OLT01 ONT 2

Reason disabled:

- Earlier private-LAN/rogue source `E4:FA:C4:B2:5E:92`
- Was seen as `192.168.88.1`
- Physical location: `000002.OLT01` `Gpon1/0/2` `ONT 2`

Commands:

```text
telnet 192.168.55.98
enable
configure
interface gpon 1/0/2
ont activate 2
exit
exit
show mac address-table address e4:fa:c4:b2:5e:92
show ont info gpon 1/0/2
```

## Notes

- `ont activate <ONU_ID>` is the rollback for `ont deactivate <ONU_ID>`.
- Do not save to startup config unless you intend the re-enable to survive reboot.
- If support gets a call, re-enable first, then verify whether the customer starts leaking a private LAN again before leaving it in service.
