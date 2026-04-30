# OLT CLI Discovery 2026-04-03

Target:
- `000002.OLT01`
- `192.168.55.98`

Method:
- live telnet CLI using the old Jake `scripts/olt_telnet_read.py`
- login confirmed with local project credentials

## Top-Level CLI

Top-level `?` returns:
- `broadcast`
- `configure`
- `copy`
- `debug`
- `enable-admin`
- `firmware`
- `logout`
- `ping`
- `reboot`
- `remove`
- `reset`
- `telnet`
- `terminal`
- `tracert`
- `clear`
- `exit`
- `history`
- `show`

Notes:
- Cisco-style `show ?` completion is not accepted directly at top level on this box.
- Incomplete-command probing is more reliable than normal `?` completion at top level.

## Working ONT Show Commands

Confirmed working:

```text
show ont info gpon 1/0/2
```

Behavior:
- lists every ONU on GPON port `1/0/2`
- includes:
  - PON ID
  - ONU ID
  - serial
  - online status
  - admin status
  - active status
  - config status
  - match status
  - line/service/management profiles

Confirmed working single-ONU syntax:

```text
show ont info gpon 1/0/2 ont 2
```

Important:
- the single-ONU syntax is `ont <onu-id>`
- the earlier guessed form `show ont info gpon 1/0/2 2` is invalid on this OLT

Confirmed working detail table:

```text
show ont info gpon 1/0/2 detail
```

This adds:
- online time
- distance
- description

Not confirmed:

```text
show ont info gpon 1/0/2 detail ont 2
```

This returned `Error: Bad command` on `000002.OLT01`.

## Interface GPON Mode

To enter GPON interface mode:

```text
configure
interface gpon 1/0/2
```

Discovery:

```text
interface gpon ?
```

Returns:
- valid range on this box includes `1/0/1-1/0/4`

Inside `config-if-gpon`, `?` returns:
- `dba-calculate-mode`
- `ddm`
- `downstream-fec`
- `ip`
- `ipv6`
- `key-exchange`
- `long-laseront`
- `mvr`
- `ont`
- `onu-isolate`
- `port-isolate`
- `qos`
- `range`
- `shutdown`
- `clear`
- `end`
- `exit`
- `history`
- `no`
- `show`

Inside `config-if-gpon`, `ont ?` returns:
- `activate`
- `add`
- `auto-auth`
- `autofind`
- `cancel`
- `catv`
- `confirm`
- `cwmp`
- `cwmp-auth-profile`
- `deactivate`
- `delete`
- `iphost`
- `modify`
- `port`
- `re-register`
- `reboot`
- `sipuser`
- `wan`
- `wan-pppoeprofile`
- `wlan`

Inside `config-if-gpon`, `show ?` returns broad read-only categories including:
- `aaa`
- `arp`
- `cpu-utilization`
- `ddm`
- `environment`
- `interface`
- `ip`
- `logging`
- `mac`
- `ont`
- `service-port`
- `system-info`
- `users`
- `vlan`

## Immediate Jake Implications

Jake should use:

```text
show ont info gpon <pon>
show ont info gpon <pon> ont <onu-id>
show ont info gpon <pon> detail
```

Jake should not use:

```text
show ont info gpon <pon> <onu-id>
show ont info gpon <pon> detail ont <onu-id>
```

## Evidence From Live Run

Live run for `Savoy1Unit3N`-linked path:

```text
show ont info gpon 1/0/2 ont 2
```

Returned:
- serial `TPLG-31A120CE`
- `online`
- `admin deactivated`
- `active inactive`
- `config failed`
- `match mismatch`

That means Jake can now inspect the real current ONU row on the OLT instead of only relying on field notes.
