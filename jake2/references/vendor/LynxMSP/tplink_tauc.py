"""
TPLink TAUC API Service
Comprehensive management for TPLink OLT and ONT devices including PizzaBox OLT 4/8 port and XZ000-G7 ONT
"""

import httpx
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TPLinkDevice:
    device_id: str
    sn: str
    mac: str
    name: str
    model: str
    status: str
    ip_address: str
    firmware_version: str
    last_seen: datetime
    device_type: str  # 'olt_pizzabox_4', 'olt_pizzabox_8', 'ont_xz000_g7'

@dataclass
class EthernetInterface:
    interface_name: str
    alias: str
    status: str  # 'up', 'down', 'disabled'
    speed: str
    duplex: str
    mtu: int
    mac_address: str
    rx_bytes: int
    tx_bytes: int
    rx_packets: int
    tx_packets: int

@dataclass
class PortConfig:
    port_id: str
    interface_name: str
    enabled: bool
    speed: str
    duplex: str
    vlan_id: Optional[int]
    description: str

class TPLinkTAUCService:
    def __init__(self, domain: str, client_id: str, client_secret: str):
        self.domain = domain
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires_at = None
        self.base_url = f"https://{domain}/v1/openapi"
        
    async def _get_access_token(self) -> str:
        """Get or refresh access token"""
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token
            
        async with httpx.AsyncClient(timeout=30.0) as client:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials"
            }
            
            response = await client.post(f"{self.base_url}/token", data=data)
            response.raise_for_status()
            
            result = response.json()
            if result.get("errorCode") != 0:
                raise Exception(f"Failed to get access token: {result.get('errorMessage')}")
                
            self.access_token = result["result"]["access_token"]
            expires_in = result["result"].get("expires_in", 3600)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)  # 1 minute buffer
            
            return self.access_token
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to TAUC API"""
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                response = await client.get(f"{self.base_url}{endpoint}", headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(f"{self.base_url}{endpoint}", headers=headers, json=data)
            elif method.upper() == "PUT":
                response = await client.put(f"{self.base_url}{endpoint}", headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = await client.delete(f"{self.base_url}{endpoint}", headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            result = response.json()
            
            if result.get("errorCode") != 0:
                raise Exception(f"API Error: {result.get('errorMessage')}")
                
            return result.get("result", {})
    
    # Device Information Methods
    async def get_device_id(self, sn: str, mac: str) -> str:
        """Get device ID by serial number and MAC address"""
        params = {"sn": sn, "mac": mac}
        result = await self._make_request("GET", "/device-information/device-id", params=params)
        return result["deviceId"]
    
    async def get_device_info(self, device_id: str) -> TPLinkDevice:
        """Get comprehensive device information"""
        result = await self._make_request("GET", f"/device-information/device-info/{device_id}")
        
        return TPLinkDevice(
            device_id=device_id,
            sn=result.get("sn", ""),
            mac=result.get("mac", ""),
            name=result.get("name", ""),
            model=result.get("model", ""),
            status=result.get("status", "unknown"),
            ip_address=result.get("ipAddress", ""),
            firmware_version=result.get("firmwareVersion", ""),
            last_seen=datetime.now(),
            device_type=self._determine_device_type(result.get("model", ""))
        )
    
    def _determine_device_type(self, model: str) -> str:
        """Determine device type based on model"""
        model_lower = model.lower()
        if "pizzabox" in model_lower:
            if "4" in model_lower:
                return "olt_pizzabox_4"
            elif "8" in model_lower:
                return "olt_pizzabox_8"
            return "olt_pizzabox"
        elif "xz000-g7" in model_lower:
            return "ont_xz000_g7"
        elif "olt" in model_lower:
            return "olt_generic"
        elif "ont" in model_lower:
            return "ont_generic"
        return "unknown"
    
    # Interface Management Methods
    async def get_ethernet_interfaces(self, network_id: str, refresh: bool = False) -> List[EthernetInterface]:
        """Get list of ethernet interfaces"""
        params = {"refresh": 1 if refresh else 0}
        result = await self._make_request("GET", f"/device-management/aginet/ethernet-interface-list/{network_id}", params=params)
        
        interfaces = []
        for interface_data in result.get("interfaces", []):
            interfaces.append(EthernetInterface(
                interface_name=interface_data.get("interfaceName", ""),
                alias=interface_data.get("alias", ""),
                status=interface_data.get("status", "unknown"),
                speed=interface_data.get("speed", ""),
                duplex=interface_data.get("duplex", ""),
                mtu=interface_data.get("mtu", 1500),
                mac_address=interface_data.get("macAddress", ""),
                rx_bytes=interface_data.get("rxBytes", 0),
                tx_bytes=interface_data.get("txBytes", 0),
                rx_packets=interface_data.get("rxPackets", 0),
                tx_packets=interface_data.get("txPackets", 0)
            ))
        
        return interfaces
    
    async def get_ip_interfaces(self, network_id: str, refresh: bool = False) -> List[Dict]:
        """Get IP interface configuration"""
        params = {"refresh": 1 if refresh else 0}
        return await self._make_request("GET", f"/device-management/aginet/ip-interface-list/{network_id}", params=params)
    
    # Port Management Methods
    async def enable_port(self, device_id: str, interface_name: str) -> bool:
        """Enable a specific ethernet port"""
        data = {
            "interfaceName": interface_name,
            "enabled": True
        }
        await self._make_request("POST", f"/device-management/aginet/interface-control/{device_id}", data=data)
        return True
    
    async def disable_port(self, device_id: str, interface_name: str) -> bool:
        """Disable a specific ethernet port"""
        data = {
            "interfaceName": interface_name,
            "enabled": False
        }
        await self._make_request("POST", f"/device-management/aginet/interface-control/{device_id}", data=data)
        return True
    
    async def configure_port(self, device_id: str, port_config: PortConfig) -> bool:
        """Configure port settings"""
        data = {
            "interfaceName": port_config.interface_name,
            "enabled": port_config.enabled,
            "speed": port_config.speed,
            "duplex": port_config.duplex,
            "description": port_config.description
        }
        if port_config.vlan_id:
            data["vlanId"] = port_config.vlan_id
            
        await self._make_request("POST", f"/device-management/aginet/interface-config/{device_id}", data=data)
        return True
    
    # OLT Specific Methods
    async def get_olt_status(self, device_id: str) -> Dict:
        """Get OLT operational status and statistics"""
        # This would map to specific OLT monitoring endpoints
        result = await self._make_request("GET", f"/device-monitoring/olt-status/{device_id}")
        return {
            "temperature": result.get("temperature", 0),
            "power_consumption": result.get("powerConsumption", 0),
            "uptime": result.get("uptime", 0),
            "pon_ports": result.get("ponPorts", []),
            "ethernet_ports": result.get("ethernetPorts", []),
            "alarm_count": result.get("alarmCount", 0)
        }
    
    async def get_pon_ports(self, device_id: str) -> List[Dict]:
        """Get PON port status for OLT"""
        return await self._make_request("GET", f"/device-management/olt/pon-ports/{device_id}")
    
    async def get_connected_onts(self, device_id: str, pon_port: Optional[str] = None) -> List[Dict]:
        """Get list of connected ONTs"""
        params = {"ponPort": pon_port} if pon_port else {}
        return await self._make_request("GET", f"/device-management/olt/connected-onts/{device_id}", params=params)
    
    async def provision_ont(self, device_id: str, ont_data: Dict) -> bool:
        """Provision a new ONT on the OLT"""
        data = {
            "ponPort": ont_data["pon_port"],
            "ontId": ont_data["ont_id"],
            "serialNumber": ont_data["serial_number"],
            "serviceProfile": ont_data.get("service_profile", "default"),
            "description": ont_data.get("description", "")
        }
        await self._make_request("POST", f"/device-management/olt/provision-ont/{device_id}", data=data)
        return True
    
    # ONT Specific Methods
    async def get_ont_status(self, device_id: str) -> Dict:
        """Get ONT operational status"""
        result = await self._make_request("GET", f"/device-monitoring/ont-status/{device_id}")
        return {
            "optical_power_rx": result.get("opticalPowerRx", 0),
            "optical_power_tx": result.get("opticalPowerTx", 0),
            "temperature": result.get("temperature", 0),
            "uptime": result.get("uptime", 0),
            "pon_status": result.get("ponStatus", "unknown"),
            "ethernet_ports": result.get("ethernetPorts", []),
            "wifi_status": result.get("wifiStatus", {})
        }
    
    async def get_ont_ethernet_ports(self, device_id: str) -> List[Dict]:
        """Get ethernet port status for ONT"""
        return await self._make_request("GET", f"/device-management/ont/ethernet-ports/{device_id}")
    
    async def configure_ont_wifi(self, device_id: str, wifi_config: Dict) -> bool:
        """Configure WiFi settings on ONT"""
        data = {
            "ssid": wifi_config["ssid"],
            "password": wifi_config["password"],
            "security": wifi_config.get("security", "WPA2"),
            "enabled": wifi_config.get("enabled", True),
            "channel": wifi_config.get("channel", "auto")
        }
        await self._make_request("POST", f"/device-management/ont/wifi-config/{device_id}", data=data)
        return True
    
    # Monitoring and Statistics
    async def get_interface_statistics(self, device_id: str, interface_name: str) -> Dict:
        """Get detailed interface statistics"""
        params = {"interface": interface_name}
        return await self._make_request("GET", f"/device-monitoring/interface-stats/{device_id}", params=params)
    
    async def get_device_alarms(self, device_id: str) -> List[Dict]:
        """Get active alarms for device"""
        return await self._make_request("GET", f"/device-monitoring/alarms/{device_id}")
    
    async def get_performance_metrics(self, device_id: str, metric_type: str = "all") -> Dict:
        """Get performance metrics"""
        params = {"type": metric_type}
        return await self._make_request("GET", f"/device-monitoring/performance/{device_id}", params=params)
    
    # Bulk Operations
    async def get_all_devices(self) -> List[TPLinkDevice]:
        """Get all managed devices"""
        result = await self._make_request("GET", "/device-information/device-list")
        devices = []
        
        for device_data in result.get("devices", []):
            devices.append(TPLinkDevice(
                device_id=device_data["deviceId"],
                sn=device_data.get("sn", ""),
                mac=device_data.get("mac", ""),
                name=device_data.get("name", ""),
                model=device_data.get("model", ""),
                status=device_data.get("status", "unknown"),
                ip_address=device_data.get("ipAddress", ""),
                firmware_version=device_data.get("firmwareVersion", ""),
                last_seen=datetime.now(),
                device_type=self._determine_device_type(device_data.get("model", ""))
            ))
        
        return devices
    
    async def bulk_port_operation(self, operations: List[Dict]) -> List[bool]:
        """Perform bulk port operations"""
        results = []
        for operation in operations:
            try:
                if operation["action"] == "enable":
                    result = await self.enable_port(operation["device_id"], operation["interface"])
                elif operation["action"] == "disable":
                    result = await self.disable_port(operation["device_id"], operation["interface"])
                else:
                    result = False
                results.append(result)
            except Exception as e:
                logger.error(f"Bulk operation failed: {e}")
                results.append(False)
        
        return results

# Factory function for creating service instances
def create_tplink_service(domain: str, client_id: str, client_secret: str) -> TPLinkTAUCService:
    """Create and return a configured TPLink TAUC service instance"""
    return TPLinkTAUCService(domain, client_id, client_secret)