"""
Network Discovery Service for LLDP and SNMP processing
Handles automatic discovery and monitoring of network devices
"""

import asyncio
import ipaddress
import socket
import struct
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from dataclasses import dataclass
import json

# SNMP imports - these would need to be installed: pip install pysnmp
try:
    from pysnmp.hlapi import *
    from pysnmp.proto.rfc1902 import OctetString
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False
    logging.warning("SNMP libraries not available. Install with: pip install pysnmp")

# LLDP packet parsing
@dataclass
class LLDPNeighbor:
    chassis_id: str
    port_id: str
    port_description: str
    system_name: str
    system_description: str
    management_address: str
    capabilities: List[str]
    discovered_at: datetime
    ttl: int

@dataclass
class SNMPDevice:
    ip_address: str
    system_name: str
    system_description: str
    system_oid: str
    uptime: int
    contact: str
    location: str
    interfaces: List[Dict]
    discovered_at: datetime

class NetworkDiscoveryService:
    def __init__(self, db: Session, company_id: int):
        self.db = db
        self.company_id = company_id
        self.logger = logging.getLogger(__name__)
        
        # Default SNMP settings - these will be overridden by company settings
        self.snmp_community = "public"
        self.snmp_version = "2c"
        self.snmp_timeout = 5
        self.snmp_retries = 3
        
        # Load company-specific settings
        self._load_settings()
    
    def _load_settings(self):
        """Load SNMP and discovery settings from company configuration"""
        try:
            from ..database import CompanySetting
            
            settings = self.db.query(CompanySetting).filter(
                CompanySetting.company_id == self.company_id,
                CompanySetting.category == 'network'
            ).all()
            
            for setting in settings:
                if setting.setting_key == 'snmp_community':
                    self.snmp_community = setting.setting_value
                elif setting.setting_key == 'snmp_version':
                    self.snmp_version = setting.setting_value
                elif setting.setting_key == 'snmp_timeout':
                    self.snmp_timeout = int(setting.setting_value)
                elif setting.setting_key == 'snmp_retries':
                    self.snmp_retries = int(setting.setting_value)
                    
        except Exception as e:
            self.logger.warning(f"Could not load network settings: {e}")
    
    async def discover_network_range(self, network: str) -> List[str]:
        """
        Discover active hosts in a network range using ping sweep
        """
        try:
            network_obj = ipaddress.ip_network(network, strict=False)
            active_hosts = []
            
            # Create ping tasks for all hosts in the network
            tasks = []
            for host in network_obj.hosts():
                if network_obj.num_addresses > 256:
                    # For large networks, sample every 10th address
                    if int(str(host).split('.')[-1]) % 10 == 0:
                        tasks.append(self._ping_host(str(host)))
                else:
                    tasks.append(self._ping_host(str(host)))
            
            # Execute ping tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if result is True:  # Host is reachable
                    if network_obj.num_addresses > 256:
                        host_ip = str(list(network_obj.hosts())[i * 10])
                    else:
                        host_ip = str(list(network_obj.hosts())[i])
                    active_hosts.append(host_ip)
            
            self.logger.info(f"Discovered {len(active_hosts)} active hosts in {network}")
            return active_hosts
            
        except Exception as e:
            self.logger.error(f"Error discovering network {network}: {e}")
            return []
    
    async def _ping_host(self, host: str) -> bool:
        """
        Ping a host to check if it's reachable
        """
        try:
            # Use asyncio subprocess for non-blocking ping
            process = await asyncio.create_subprocess_exec(
                'ping', '-c', '1', '-W', '1', host,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            await asyncio.wait_for(process.wait(), timeout=2)
            return process.returncode == 0
            
        except (asyncio.TimeoutError, Exception):
            return False
    
    def snmp_walk(self, host: str, oid: str) -> List[Tuple[str, str]]:
        """
        Perform SNMP walk to retrieve multiple OID values
        """
        if not SNMP_AVAILABLE:
            self.logger.error("SNMP libraries not available")
            return []
        
        try:
            results = []
            
            for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                SnmpEngine(),
                CommunityData(self.snmp_community),
                UdpTransportTarget((host, 161), timeout=self.snmp_timeout, retries=self.snmp_retries),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False
            ):
                
                if errorIndication:
                    self.logger.error(f"SNMP error for {host}: {errorIndication}")
                    break
                    
                if errorStatus:
                    self.logger.error(f"SNMP error for {host}: {errorStatus.prettyPrint()}")
                    break
                
                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    value_str = str(varBind[1])
                    results.append((oid_str, value_str))
            
            return results
            
        except Exception as e:
            self.logger.error(f"SNMP walk error for {host}: {e}")
            return []
    
    def snmp_get(self, host: str, oids: List[str]) -> Dict[str, str]:
        """
        Perform SNMP GET to retrieve specific OID values
        """
        if not SNMP_AVAILABLE:
            self.logger.error("SNMP libraries not available")
            return {}
        
        try:
            results = {}
            
            for (errorIndication, errorStatus, errorIndex, varBinds) in getCmd(
                SnmpEngine(),
                CommunityData(self.snmp_community),
                UdpTransportTarget((host, 161), timeout=self.snmp_timeout, retries=self.snmp_retries),
                ContextData(),
                *[ObjectType(ObjectIdentity(oid)) for oid in oids]
            ):
                
                if errorIndication:
                    self.logger.error(f"SNMP error for {host}: {errorIndication}")
                    return {}
                    
                if errorStatus:
                    self.logger.error(f"SNMP error for {host}: {errorStatus.prettyPrint()}")
                    return {}
                
                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    value_str = str(varBind[1])
                    results[oid_str] = value_str
            
            return results
            
        except Exception as e:
            self.logger.error(f"SNMP get error for {host}: {e}")
            return {}
    
    async def discover_device_via_snmp(self, host: str) -> Optional[SNMPDevice]:
        """
        Discover device information via SNMP
        """
        if not SNMP_AVAILABLE:
            self.logger.error("SNMP libraries not available")
            return None
        
        try:
            # Standard SNMP MIB OIDs
            system_oids = [
                '1.3.6.1.2.1.1.1.0',  # sysDescr
                '1.3.6.1.2.1.1.2.0',  # sysObjectID
                '1.3.6.1.2.1.1.3.0',  # sysUpTime
                '1.3.6.1.2.1.1.4.0',  # sysContact
                '1.3.6.1.2.1.1.5.0',  # sysName
                '1.3.6.1.2.1.1.6.0'   # sysLocation
            ]
            
            # Get basic system information
            system_info = self.snmp_get(host, system_oids)
            
            if not system_info:
                return None
            
            # Get interface information
            interfaces = self._get_snmp_interfaces(host)
            
            device = SNMPDevice(
                ip_address=host,
                system_name=system_info.get('1.3.6.1.2.1.1.5.0', 'Unknown'),
                system_description=system_info.get('1.3.6.1.2.1.1.1.0', 'Unknown'),
                system_oid=system_info.get('1.3.6.1.2.1.1.2.0', 'Unknown'),
                uptime=int(system_info.get('1.3.6.1.2.1.1.3.0', '0')),
                contact=system_info.get('1.3.6.1.2.1.1.4.0', 'Unknown'),
                location=system_info.get('1.3.6.1.2.1.1.6.0', 'Unknown'),
                interfaces=interfaces,
                discovered_at=datetime.utcnow()
            )
            
            return device
            
        except Exception as e:
            self.logger.error(f"Error discovering device {host} via SNMP: {e}")
            return None
    
    def _get_snmp_interfaces(self, host: str) -> List[Dict]:
        """
        Get interface information via SNMP
        """
        try:
            interfaces = []
            
            # Get interface descriptions
            if_descr_results = self.snmp_walk(host, '1.3.6.1.2.1.2.2.1.2')  # ifDescr
            if_type_results = self.snmp_walk(host, '1.3.6.1.2.1.2.2.1.3')   # ifType
            if_mtu_results = self.snmp_walk(host, '1.3.6.1.2.1.2.2.1.4')    # ifMtu
            if_speed_results = self.snmp_walk(host, '1.3.6.1.2.1.2.2.1.5')  # ifSpeed
            if_admin_results = self.snmp_walk(host, '1.3.6.1.2.1.2.2.1.7')  # ifAdminStatus
            if_oper_results = self.snmp_walk(host, '1.3.6.1.2.1.2.2.1.8')   # ifOperStatus
            
            # Combine interface data
            interface_data = {}
            
            for oid, value in if_descr_results:
                if_index = oid.split('.')[-1]
                interface_data[if_index] = {'description': value}
            
            for oid, value in if_type_results:
                if_index = oid.split('.')[-1]
                if if_index in interface_data:
                    interface_data[if_index]['type'] = value
            
            for oid, value in if_mtu_results:
                if_index = oid.split('.')[-1]
                if if_index in interface_data:
                    interface_data[if_index]['mtu'] = value
            
            for oid, value in if_speed_results:
                if_index = oid.split('.')[-1]
                if if_index in interface_data:
                    interface_data[if_index]['speed'] = value
            
            for oid, value in if_admin_results:
                if_index = oid.split('.')[-1]
                if if_index in interface_data:
                    interface_data[if_index]['admin_status'] = value
            
            for oid, value in if_oper_results:
                if_index = oid.split('.')[-1]
                if if_index in interface_data:
                    interface_data[if_index]['oper_status'] = value
            
            # Convert to list format
            for if_index, data in interface_data.items():
                interfaces.append({
                    'index': if_index,
                    'description': data.get('description', 'Unknown'),
                    'type': data.get('type', 'Unknown'),
                    'mtu': data.get('mtu', '1500'),
                    'speed': data.get('speed', '0'),
                    'admin_status': data.get('admin_status', 'Unknown'),
                    'oper_status': data.get('oper_status', 'Unknown')
                })
            
            return interfaces
            
        except Exception as e:
            self.logger.error(f"Error getting interfaces for {host}: {e}")
            return []
    
    async def discover_lldp_neighbors(self, host: str) -> List[LLDPNeighbor]:
        """
        Discover LLDP neighbors via SNMP
        """
        if not SNMP_AVAILABLE:
            self.logger.error("SNMP libraries not available")
            return []
        
        try:
            neighbors = []
            
            # LLDP MIB OIDs
            lldp_chassis_id_oid = '1.0.8802.1.1.2.1.4.1.1.5'     # lldpRemChassisId
            lldp_port_id_oid = '1.0.8802.1.1.2.1.4.1.1.7'       # lldpRemPortId
            lldp_port_desc_oid = '1.0.8802.1.1.2.1.4.1.1.8'     # lldpRemPortDesc
            lldp_sys_name_oid = '1.0.8802.1.1.2.1.4.1.1.9'      # lldpRemSysName
            lldp_sys_desc_oid = '1.0.8802.1.1.2.1.4.1.1.10'     # lldpRemSysDesc
            lldp_sys_cap_oid = '1.0.8802.1.1.2.1.4.1.1.11'      # lldpRemSysCapSupported
            lldp_mgmt_addr_oid = '1.0.8802.1.1.2.1.4.2.1.3'     # lldpRemManAddr
            
            # Get LLDP neighbor information
            chassis_results = self.snmp_walk(host, lldp_chassis_id_oid)
            port_results = self.snmp_walk(host, lldp_port_id_oid)
            port_desc_results = self.snmp_walk(host, lldp_port_desc_oid)
            sys_name_results = self.snmp_walk(host, lldp_sys_name_oid)
            sys_desc_results = self.snmp_walk(host, lldp_sys_desc_oid)
            mgmt_addr_results = self.snmp_walk(host, lldp_mgmt_addr_oid)
            
            # Process LLDP data
            lldp_data = {}
            
            for oid, value in chassis_results:
                neighbor_key = '.'.join(oid.split('.')[-3:])  # Extract time mark, local port, remote index
                lldp_data[neighbor_key] = {'chassis_id': value}
            
            for oid, value in port_results:
                neighbor_key = '.'.join(oid.split('.')[-3:])
                if neighbor_key in lldp_data:
                    lldp_data[neighbor_key]['port_id'] = value
            
            for oid, value in port_desc_results:
                neighbor_key = '.'.join(oid.split('.')[-3:])
                if neighbor_key in lldp_data:
                    lldp_data[neighbor_key]['port_description'] = value
            
            for oid, value in sys_name_results:
                neighbor_key = '.'.join(oid.split('.')[-3:])
                if neighbor_key in lldp_data:
                    lldp_data[neighbor_key]['system_name'] = value
            
            for oid, value in sys_desc_results:
                neighbor_key = '.'.join(oid.split('.')[-3:])
                if neighbor_key in lldp_data:
                    lldp_data[neighbor_key]['system_description'] = value
            
            for oid, value in mgmt_addr_results:
                neighbor_key = '.'.join(oid.split('.')[-4:-1])  # Different indexing for management address
                if neighbor_key in lldp_data:
                    lldp_data[neighbor_key]['management_address'] = value
            
            # Convert to LLDPNeighbor objects
            for neighbor_data in lldp_data.values():
                if 'chassis_id' in neighbor_data and 'port_id' in neighbor_data:
                    neighbor = LLDPNeighbor(
                        chassis_id=neighbor_data.get('chassis_id', ''),
                        port_id=neighbor_data.get('port_id', ''),
                        port_description=neighbor_data.get('port_description', ''),
                        system_name=neighbor_data.get('system_name', ''),
                        system_description=neighbor_data.get('system_description', ''),
                        management_address=neighbor_data.get('management_address', ''),
                        capabilities=[],  # Would need additional parsing
                        discovered_at=datetime.utcnow(),
                        ttl=120  # Default TTL
                    )
                    neighbors.append(neighbor)
            
            return neighbors
            
        except Exception as e:
            self.logger.error(f"Error discovering LLDP neighbors for {host}: {e}")
            return []
    
    async def full_network_discovery(self, network_ranges: List[str]) -> Dict[str, any]:
        """
        Perform comprehensive network discovery including ping sweep, SNMP, and LLDP
        """
        discovery_results = {
            'started_at': datetime.utcnow(),
            'network_ranges': network_ranges,
            'active_hosts': [],
            'snmp_devices': [],
            'lldp_neighbors': [],
            'errors': []
        }
        
        try:
            # Discover active hosts in all network ranges
            all_active_hosts = []
            for network in network_ranges:
                active_hosts = await self.discover_network_range(network)
                all_active_hosts.extend(active_hosts)
            
            discovery_results['active_hosts'] = all_active_hosts
            
            # Discover devices via SNMP
            snmp_tasks = [self.discover_device_via_snmp(host) for host in all_active_hosts]
            snmp_results = await asyncio.gather(*snmp_tasks, return_exceptions=True)
            
            for result in snmp_results:
                if isinstance(result, SNMPDevice):
                    discovery_results['snmp_devices'].append(result)
                elif isinstance(result, Exception):
                    discovery_results['errors'].append(str(result))
            
            # Discover LLDP neighbors for SNMP-responsive devices
            lldp_tasks = []
            for device in discovery_results['snmp_devices']:
                lldp_tasks.append(self.discover_lldp_neighbors(device.ip_address))
            
            lldp_results = await asyncio.gather(*lldp_tasks, return_exceptions=True)
            
            for result in lldp_results:
                if isinstance(result, list):
                    discovery_results['lldp_neighbors'].extend(result)
                elif isinstance(result, Exception):
                    discovery_results['errors'].append(str(result))
            
            discovery_results['completed_at'] = datetime.utcnow()
            
            return discovery_results
            
        except Exception as e:
            self.logger.error(f"Error in full network discovery: {e}")
            discovery_results['errors'].append(str(e))
            discovery_results['completed_at'] = datetime.utcnow()
            return discovery_results

    def save_discovery_results(self, results: Dict[str, any]):
        """
        Save discovery results to database
        """
        try:
            from ..database import (NetworkMonitoring, Site, Router, NetworkInterface, LLDPNeighborRecord)
            
            # Save discovered devices as monitoring entries
            for device in results.get('snmp_devices', []):
                # Check if router already exists
                existing_router = self.db.query(Router).filter(
                    Router.management_ip == device.ip_address,
                    Router.company_id == self.company_id
                ).first()
                
                if not existing_router:
                    # Create new router entry
                    new_router = Router(
                        name=device.system_name or f"Device-{device.ip_address}",
                        model="Unknown",
                        management_ip=device.ip_address,
                        username="admin",  # Default - should be configured
                        password="admin",  # Default - should be configured
                        site_id=None,  # Would need to be assigned
                        status="discovered",
                        company_id=self.company_id,
                        os_version=device.system_description
                    )
                    self.db.add(new_router)
                    self.db.flush()
                    router_id = new_router.id
                else:
                    router_id = existing_router.id
                
                # Add monitoring metrics
                monitoring_entry = NetworkMonitoring(
                    router_id=router_id,
                    metric_type="discovery",
                    metric_value=1.0,
                    metric_unit="boolean"
                )
                self.db.add(monitoring_entry)

            # Save LLDP neighbors
            for neighbor in results.get('lldp_neighbors', []):
                lldp_entry = LLDPNeighborRecord(
                    company_id=self.company_id,
                    router_id=None,
                    device_ip=neighbor.management_address or "",
                    chassis_id=neighbor.chassis_id,
                    port_id=neighbor.port_id,
                    port_description=neighbor.port_description,
                    system_name=neighbor.system_name,
                    system_description=neighbor.system_description,
                    management_address=neighbor.management_address,
                    capabilities=neighbor.capabilities,
                    discovered_at=neighbor.discovered_at,
                    ttl=neighbor.ttl
                )
                self.db.add(lldp_entry)
            
            self.db.commit()
            self.logger.info(f"Saved discovery results for {len(results.get('snmp_devices', []))} devices")
            
        except Exception as e:
            self.logger.error(f"Error saving discovery results: {e}")
            self.db.rollback()

# Utility functions for LLDP packet parsing (if raw LLDP packets are captured)
def parse_lldp_packet(packet_data: bytes) -> Optional[LLDPNeighbor]:
    """
    Parse raw LLDP packet data
    This is a simplified implementation - full LLDP parsing is quite complex
    """
    try:
        # LLDP packet structure parsing would go here
        # This is a placeholder implementation
        return None
    except Exception:
        return None

def create_discovery_service(db: Session, company_id: int) -> NetworkDiscoveryService:
    """
    Factory function to create a NetworkDiscoveryService instance
    """
    return NetworkDiscoveryService(db, company_id)
