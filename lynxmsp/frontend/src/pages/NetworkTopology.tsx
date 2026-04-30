import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  Chip,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  Switch,
  FormControlLabel,
  LinearProgress
} from '@mui/material';
import {
  Router as RouterIcon,
  Memory,
  NetworkCheck,
  Cable,
  Refresh,
  Info,
  Warning,
  CheckCircle,
  Error,
  Hub,
  Computer,
  Settings,
  LocationOn,
  Inventory,
  FiberManualRecord,
  Add,
  Edit,
  Delete,
  Search
} from '@mui/icons-material';
import api from '../services/api';

interface Site {
  id: number;
  name: string;
  location: string;
  type: string;
  routers: number;
  customers: number;
  status: string;
}

interface RouterInfo {
  id: number;
  name: string;
  model: string;
  ip_address: string;
  status: string;
  uptime?: string;
  cpu_usage?: number;
  memory_usage?: number;
  interfaces: NetworkInterface[];
}

interface NetworkInterface {
  name: string;
  status: string;
  ip: string;
}

interface Equipment {
  id: number;
  name: string;
  type: string;
  model: string;
  serial_number: string;
  status: string;
  location: string;
}

interface Subnet {
  id: number;
  name: string;
  network: string;
  vlan_id: number;
  type: string;
  assignments: number;
}

interface OLTDevice {
  id: number;
  name: string;
  ip_address: string;
  model: string;
  firmware_version: string;
  onus_connected: number;
  max_onus: number;
  status: 'online' | 'offline' | 'maintenance';
  location?: string;
  serial_number: string;
  uptime?: string;
  created_at: string;
}

interface IPSubnet {
  id: number;
  name: string;
  network: string;
  mask: string;
  vlan_id: number;
  gateway: string;
  dhcp_enabled: boolean;
  dhcp_range_start?: string;
  dhcp_range_end?: string;
  type: 'customer' | 'management' | 'infrastructure';
  site_id?: number;
  utilization: number;
  created_at: string;
}

interface NetworkSite {
  id: number;
  name: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  coordinates?: { lat: number; lng: number };
  type: 'datacenter' | 'pop' | 'customer_premises' | 'tower';
  status: 'active' | 'inactive' | 'maintenance';
  contact_name?: string;
  contact_phone?: string;
  created_at: string;
}

interface NetworkEquipment {
  id: number;
  name: string;
  type: 'router' | 'switch' | 'firewall' | 'server' | 'ups' | 'patch_panel' | 'other';
  manufacturer: string;
  model: string;
  serial_number: string;
  asset_tag?: string;
  site_id: number;
  rack_location?: string;
  status: 'active' | 'inactive' | 'maintenance' | 'retired';
  purchase_date?: string;
  warranty_expiry?: string;
  notes?: string;
  created_at: string;
}

interface FiberConnection {
  id: number;
  connection_name: string;
  from_site_id: number;
  to_site_id: number;
  from_equipment?: string;
  to_equipment?: string;
  fiber_type: 'single_mode' | 'multi_mode';
  fiber_count: number;
  length_km: number;
  status: 'active' | 'inactive' | 'maintenance';
  provider?: string;
  circuit_id?: string;
  installation_date?: string;
  notes?: string;
  created_at: string;
}

interface TopologyData {
  site: {
    id: number;
    name: string;
    location: string;
    coordinates?: { lat: number; lng: number };
  };
  routers: RouterInfo[];
  equipment: Equipment[];
  subnets: Subnet[];
}

const NetworkTopology: React.FC = () => {
  const location = useLocation();
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSite, setSelectedSite] = useState<number | ''>('');
  const [topologyData, setTopologyData] = useState<TopologyData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRouter, setSelectedRouter] = useState<RouterInfo | null>(null);
  const [routerDialogOpen, setRouterDialogOpen] = useState(false);

  // CRUD State Management
  const [oltDevices, setOltDevices] = useState<OLTDevice[]>([]);
  const [ipSubnets, setIpSubnets] = useState<IPSubnet[]>([]);
  const [networkSites, setNetworkSites] = useState<NetworkSite[]>([]);
  const [equipmentList, setEquipmentList] = useState<NetworkEquipment[]>([]);
  const [fiberConnections, setFiberConnections] = useState<FiberConnection[]>([]);

  // Dialog States
  const [oltDialogOpen, setOltDialogOpen] = useState(false);
  const [subnetDialogOpen, setSubnetDialogOpen] = useState(false);
  const [siteDialogOpen, setSiteDialogOpen] = useState(false);
  const [equipmentDialogOpen, setEquipmentDialogOpen] = useState(false);
  const [fiberDialogOpen, setFiberDialogOpen] = useState(false);

  // Selected Items for Editing
  const [selectedOlt, setSelectedOlt] = useState<OLTDevice | null>(null);
  const [selectedSubnet, setSelectedSubnet] = useState<IPSubnet | null>(null);
  const [selectedNetworkSite, setSelectedNetworkSite] = useState<NetworkSite | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<NetworkEquipment | null>(null);
  const [selectedFiber, setSelectedFiber] = useState<FiberConnection | null>(null);

  // Form States
  const [oltForm, setOltForm] = useState({
    name: '',
    ip_address: '',
    model: '',
    firmware_version: '',
    max_onus: 32,
    location: '',
    serial_number: '',
    status: 'online' as const
  });

  const [subnetForm, setSubnetForm] = useState({
    name: '',
    network: '',
    mask: '',
    vlan_id: 1,
    gateway: '',
    dhcp_enabled: false,
    dhcp_range_start: '',
    dhcp_range_end: '',
    type: 'customer' as const,
    site_id: ''
  });

  const [siteForm, setSiteForm] = useState({
    name: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    coordinates_lat: '',
    coordinates_lng: '',
    type: 'pop' as const,
    status: 'active' as const,
    contact_name: '',
    contact_phone: ''
  });

  const [equipmentForm, setEquipmentForm] = useState({
    name: '',
    type: 'router' as const,
    manufacturer: '',
    model: '',
    serial_number: '',
    asset_tag: '',
    site_id: '',
    rack_location: '',
    status: 'active' as const,
    purchase_date: '',
    warranty_expiry: '',
    notes: ''
  });

  const [fiberForm, setFiberForm] = useState({
    connection_name: '',
    from_site_id: '',
    to_site_id: '',
    from_equipment: '',
    to_equipment: '',
    fiber_type: 'single_mode' as const,
    fiber_count: 1,
    length_km: 0,
    status: 'active' as const,
    provider: '',
    circuit_id: '',
    installation_date: '',
    notes: ''
  });

  // Route detection
  const getCurrentRoute = () => {
    const path = location.pathname;
    if (path.includes('/olt-management')) return 'olt-management';
    if (path.includes('/ip-management')) return 'ip-management';
    if (path.includes('/sites')) return 'sites';
    if (path.includes('/equipment')) return 'equipment';
    if (path.includes('/fiber-management')) return 'fiber-management';
    return 'network-topology';
  };

  const getRouteConfig = () => {
    const route = getCurrentRoute();
    switch (route) {
      case 'olt-management':
        return {
          title: 'OLT/ONU Management',
          icon: <Settings />,
          description: 'Manage Optical Line Terminals and Optical Network Units'
        };
      case 'ip-management':
        return {
          title: 'IP Management',
          icon: <Cable />,
          description: 'Manage IP addresses, subnets, and VLAN configurations'
        };
      case 'sites':
        return {
          title: 'Sites & Locations',
          icon: <LocationOn />,
          description: 'Manage network sites and physical locations'
        };
      case 'equipment':
        return {
          title: 'Equipment Inventory',
          icon: <Inventory />,
          description: 'Track and manage network equipment and hardware'
        };
      case 'fiber-management':
        return {
          title: 'Fiber Management',
          icon: <FiberManualRecord />,
          description: 'Manage fiber optic cables and connections'
        };
      default:
        return {
          title: 'Network Topology',
          icon: <NetworkCheck />,
          description: 'View and manage network infrastructure topology'
        };
    }
  };

  useEffect(() => {
    fetchSites();
    loadOLTDevices();
    loadIPSubnets();
    loadNetworkSites();
    loadEquipment();
    loadFiberConnections();
  }, []);

  const fetchSites = async () => {
    try {
      const response = await api.get('/dashboard/network-overview');
      setSites(response.data.sites);
    } catch (err) {
      setError('Failed to load sites');
    }
  };

  const fetchTopologyData = async (siteId: number) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get(`/sites/${siteId}/network-topology`);
      setTopologyData(response.data);
    } catch (err) {
      setError('Failed to load topology data');
    } finally {
      setLoading(false);
    }
  };

  const handleSiteChange = (siteId: number) => {
    setSelectedSite(siteId);
    fetchTopologyData(siteId);
  };

  const handleRouterClick = (router: RouterInfo) => {
    setSelectedRouter(router);
    setRouterDialogOpen(true);
  };

  // Data Loading Functions
  const loadOLTDevices = async () => {
    try {
      const response = await api.get('/api/v1/network/olt-devices');
      setOltDevices(response.data || []);
    } catch (err) {
      console.error('Failed to load OLT devices:', err);
      setOltDevices([]);
    }
  };

  const loadIPSubnets = async () => {
    try {
      const response = await api.get('/api/v1/network/ip-subnets');
      setIpSubnets(response.data || []);
    } catch (err) {
      console.error('Failed to load IP subnets:', err);
      setIpSubnets([]);
    }
  };

  const loadNetworkSites = async () => {
    try {
      const response = await api.get('/api/v1/network/sites');
      setNetworkSites(response.data || []);
    } catch (err) {
      console.error('Failed to load network sites:', err);
      setNetworkSites([]);
    }
  };

  const loadEquipment = async () => {
    try {
      const response = await api.get('/api/v1/network/equipment');
      setEquipmentList(response.data || []);
    } catch (err) {
      console.error('Failed to load equipment:', err);
      setEquipmentList([]);
    }
  };

  const loadFiberConnections = async () => {
    try {
      const response = await api.get('/api/v1/network/fiber-connections');
      setFiberConnections(response.data || []);
    } catch (err) {
      console.error('Failed to load fiber connections:', err);
      setFiberConnections([]);
    }
  };

  // OLT Device CRUD Operations
  const handleCreateOLT = async () => {
    try {
      await api.post('/api/v1/network/olt-devices', oltForm);
      setOltDialogOpen(false);
      resetOLTForm();
      loadOLTDevices();
    } catch (err) {
      setError('Failed to create OLT device');
      console.error('Error creating OLT device:', err);
    }
  };

  const handleEditOLT = (olt: OLTDevice) => {
    setSelectedOlt(olt);
    setOltForm({
      name: olt.name,
      ip_address: olt.ip_address,
      model: olt.model,
      firmware_version: olt.firmware_version,
      max_onus: olt.max_onus,
      location: olt.location || '',
      serial_number: olt.serial_number,
      status: olt.status as any
    });
    setOltDialogOpen(true);
  };

  const handleDeleteOLT = async (oltId: number) => {
    if (window.confirm('Are you sure you want to delete this OLT device?')) {
      try {
        await api.delete(`/api/v1/network/olt-devices/${oltId}`);
        loadOLTDevices();
      } catch (err) {
        setError('Failed to delete OLT device');
        console.error('Error deleting OLT device:', err);
      }
    }
  };

  const resetOLTForm = () => {
    setOltForm({
      name: '',
      ip_address: '',
      model: '',
      firmware_version: '',
      max_onus: 32,
      location: '',
      serial_number: '',
      status: 'online'
    });
    setSelectedOlt(null);
  };

  // IP Subnet CRUD Operations
  const handleCreateSubnet = async () => {
    try {
      const payload = {
        ...subnetForm,
        site_id: subnetForm.site_id ? parseInt(subnetForm.site_id) : null
      };
      await api.post('/api/v1/network/ip-subnets', payload);
      setSubnetDialogOpen(false);
      resetSubnetForm();
      loadIPSubnets();
    } catch (err) {
      setError('Failed to create IP subnet');
      console.error('Error creating IP subnet:', err);
    }
  };

  const handleEditSubnet = (subnet: IPSubnet) => {
    setSelectedSubnet(subnet);
    setSubnetForm({
      name: subnet.name,
      network: subnet.network,
      mask: subnet.mask,
      vlan_id: subnet.vlan_id,
      gateway: subnet.gateway,
      dhcp_enabled: subnet.dhcp_enabled,
      dhcp_range_start: subnet.dhcp_range_start || '',
      dhcp_range_end: subnet.dhcp_range_end || '',
      type: subnet.type as any,
      site_id: subnet.site_id?.toString() || ''
    });
    setSubnetDialogOpen(true);
  };

  const handleDeleteSubnet = async (subnetId: number) => {
    if (window.confirm('Are you sure you want to delete this IP subnet?')) {
      try {
        await api.delete(`/api/v1/network/ip-subnets/${subnetId}`);
        loadIPSubnets();
      } catch (err) {
        setError('Failed to delete IP subnet');
        console.error('Error deleting IP subnet:', err);
      }
    }
  };

  const resetSubnetForm = () => {
    setSubnetForm({
      name: '',
      network: '',
      mask: '',
      vlan_id: 1,
      gateway: '',
      dhcp_enabled: false,
      dhcp_range_start: '',
      dhcp_range_end: '',
      type: 'customer',
      site_id: ''
    });
    setSelectedSubnet(null);
  };

  // Site Management CRUD Operations
  const handleCreateSite = async () => {
    try {
      const payload = {
        ...siteForm,
        coordinates: siteForm.coordinates_lat && siteForm.coordinates_lng ? {
          lat: parseFloat(siteForm.coordinates_lat),
          lng: parseFloat(siteForm.coordinates_lng)
        } : undefined
      };
      await api.post('/api/v1/network/sites', payload);
      setSiteDialogOpen(false);
      resetSiteForm();
      loadNetworkSites();
    } catch (err) {
      setError('Failed to create network site');
      console.error('Error creating network site:', err);
    }
  };

  const handleEditSite = (site: NetworkSite) => {
    setSelectedNetworkSite(site);
    setSiteForm({
      name: site.name,
      address: site.address,
      city: site.city,
      state: site.state,
      zip_code: site.zip_code,
      coordinates_lat: site.coordinates?.lat.toString() || '',
      coordinates_lng: site.coordinates?.lng.toString() || '',
      type: site.type as any,
      status: site.status as any,
      contact_name: site.contact_name || '',
      contact_phone: site.contact_phone || ''
    });
    setSiteDialogOpen(true);
  };

  const handleDeleteSite = async (siteId: number) => {
    if (window.confirm('Are you sure you want to delete this network site?')) {
      try {
        await api.delete(`/api/v1/network/sites/${siteId}`);
        loadNetworkSites();
      } catch (err) {
        setError('Failed to delete network site');
        console.error('Error deleting network site:', err);
      }
    }
  };

  const resetSiteForm = () => {
    setSiteForm({
      name: '',
      address: '',
      city: '',
      state: '',
      zip_code: '',
      coordinates_lat: '',
      coordinates_lng: '',
      type: 'pop',
      status: 'active',
      contact_name: '',
      contact_phone: ''
    });
    setSelectedNetworkSite(null);
  };

  // Equipment CRUD Operations
  const handleCreateEquipment = async () => {
    try {
      const payload = {
        ...equipmentForm,
        site_id: equipmentForm.site_id ? parseInt(equipmentForm.site_id) : null
      };
      if (selectedEquipment) {
        await api.put(`/api/v1/network/equipment/${selectedEquipment.id}`, payload);
      } else {
        await api.post('/api/v1/network/equipment', payload);
      }
      setEquipmentDialogOpen(false);
      resetEquipmentForm();
      loadEquipment();
    } catch (err) {
      setError('Failed to save equipment');
      console.error('Error saving equipment:', err);
    }
  };

  const handleEditEquipment = (equipment: NetworkEquipment) => {
    setSelectedEquipment(equipment);
    setEquipmentForm({
      name: equipment.name,
      type: equipment.type as any,
      manufacturer: equipment.manufacturer,
      model: equipment.model,
      serial_number: equipment.serial_number,
      asset_tag: equipment.asset_tag || '',
      site_id: equipment.site_id?.toString() || '',
      rack_location: equipment.rack_location || '',
      status: equipment.status as any,
      purchase_date: equipment.purchase_date || '',
      warranty_expiry: equipment.warranty_expiry || '',
      notes: equipment.notes || ''
    });
    setEquipmentDialogOpen(true);
  };

  const handleDeleteEquipment = async (equipmentId: number) => {
    if (window.confirm('Are you sure you want to delete this equipment?')) {
      try {
        await api.delete(`/api/v1/network/equipment/${equipmentId}`);
        loadEquipment();
      } catch (err) {
        setError('Failed to delete equipment');
        console.error('Error deleting equipment:', err);
      }
    }
  };

  const resetEquipmentForm = () => {
    setEquipmentForm({
      name: '',
      type: 'router',
      manufacturer: '',
      model: '',
      serial_number: '',
      asset_tag: '',
      site_id: '',
      rack_location: '',
      status: 'active',
      purchase_date: '',
      warranty_expiry: '',
      notes: ''
    });
    setSelectedEquipment(null);
  };

  // Fiber Connection CRUD Operations
  const handleCreateFiber = async () => {
    try {
      const payload = {
        ...fiberForm,
        from_site_id: fiberForm.from_site_id ? parseInt(fiberForm.from_site_id) : null,
        to_site_id: fiberForm.to_site_id ? parseInt(fiberForm.to_site_id) : null
      };
      if (selectedFiber) {
        await api.put(`/api/v1/network/fiber-connections/${selectedFiber.id}`, payload);
      } else {
        await api.post('/api/v1/network/fiber-connections', payload);
      }
      setFiberDialogOpen(false);
      resetFiberForm();
      loadFiberConnections();
    } catch (err) {
      setError('Failed to save fiber connection');
      console.error('Error saving fiber connection:', err);
    }
  };

  const handleEditFiber = (fiber: FiberConnection) => {
    setSelectedFiber(fiber);
    setFiberForm({
      connection_name: fiber.connection_name,
      from_site_id: fiber.from_site_id.toString(),
      to_site_id: fiber.to_site_id.toString(),
      from_equipment: fiber.from_equipment || '',
      to_equipment: fiber.to_equipment || '',
      fiber_type: fiber.fiber_type as any,
      fiber_count: fiber.fiber_count,
      length_km: fiber.length_km,
      status: fiber.status as any,
      provider: fiber.provider || '',
      circuit_id: fiber.circuit_id || '',
      installation_date: fiber.installation_date || '',
      notes: fiber.notes || ''
    });
    setFiberDialogOpen(true);
  };

  const handleDeleteFiber = async (fiberId: number) => {
    if (window.confirm('Are you sure you want to delete this fiber connection?')) {
      try {
        await api.delete(`/api/v1/network/fiber-connections/${fiberId}`);
        loadFiberConnections();
      } catch (err) {
        setError('Failed to delete fiber connection');
        console.error('Error deleting fiber connection:', err);
      }
    }
  };

  const resetFiberForm = () => {
    setFiberForm({
      connection_name: '',
      from_site_id: '',
      to_site_id: '',
      from_equipment: '',
      to_equipment: '',
      fiber_type: 'single_mode',
      fiber_count: 1,
      length_km: 0,
      status: 'active',
      provider: '',
      circuit_id: '',
      installation_date: '',
      notes: ''
    });
    setSelectedFiber(null);
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
      case 'online':
        return 'success';
      case 'inactive':
      case 'offline':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
      case 'online':
        return <CheckCircle color="success" />;
      case 'inactive':
      case 'offline':
        return <Error color="error" />;
      case 'warning':
        return <Warning color="warning" />;
      default:
        return <Info color="info" />;
    }
  };

  const renderOLTManagement = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">OLT Devices</Typography>
              <Button 
                startIcon={<Add />} 
                variant="contained"
                onClick={() => setOltDialogOpen(true)}
              >
                Add OLT
              </Button>
            </Box>
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Device Name</TableCell>
                    <TableCell>IP Address</TableCell>
                    <TableCell>Model</TableCell>
                    <TableCell>ONUs Connected</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {oltDevices.length > 0 ? (
                    oltDevices.map((olt) => (
                      <TableRow key={olt.id}>
                        <TableCell>{olt.name}</TableCell>
                        <TableCell>{olt.ip_address}</TableCell>
                        <TableCell>{olt.model}</TableCell>
                        <TableCell>{olt.onus_connected}/{olt.max_onus}</TableCell>
                        <TableCell>
                          <Chip 
                            label={olt.status} 
                            color={getStatusColor(olt.status)}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => handleEditOLT(olt)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDeleteOLT(olt.id)}>
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={6} sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No OLT devices configured. Click "Add OLT" to get started.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>ONU Status Overview</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {oltDevices.reduce((sum, olt) => sum + olt.onus_connected, 0)}
                    </Typography>
                    <Typography variant="body2">Online ONUs</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="text.secondary">
                      {oltDevices.reduce((sum, olt) => sum + (olt.max_onus - olt.onus_connected), 0)}
                    </Typography>
                    <Typography variant="body2">Available Ports</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>OLT Status Summary</Typography>
            <Grid container spacing={2}>
              <Grid item xs={4}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {oltDevices.filter(olt => olt.status === 'online').length}
                    </Typography>
                    <Typography variant="body2">Online</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={4}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="error.main">
                      {oltDevices.filter(olt => olt.status === 'offline').length}
                    </Typography>
                    <Typography variant="body2">Offline</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={4}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="warning.main">
                      {oltDevices.filter(olt => olt.status === 'maintenance').length}
                    </Typography>
                    <Typography variant="body2">Maintenance</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderIPManagement = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">IP Subnets</Typography>
              <Button 
                startIcon={<Add />} 
                variant="contained"
                onClick={() => setSubnetDialogOpen(true)}
              >
                Add Subnet
              </Button>
            </Box>
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Subnet Name</TableCell>
                    <TableCell>Network</TableCell>
                    <TableCell>Gateway</TableCell>
                    <TableCell>VLAN ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>DHCP</TableCell>
                    <TableCell>Utilization</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {ipSubnets.length > 0 ? (
                    ipSubnets.map((subnet) => (
                      <TableRow key={subnet.id}>
                        <TableCell>{subnet.name}</TableCell>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {subnet.network}/{subnet.mask}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {subnet.gateway}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip label={`VLAN ${subnet.vlan_id}`} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={subnet.type} 
                            size="small"
                            color={subnet.type === 'customer' ? 'primary' : subnet.type === 'management' ? 'warning' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={subnet.dhcp_enabled ? 'Enabled' : 'Disabled'} 
                            size="small"
                            color={subnet.dhcp_enabled ? 'success' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <LinearProgress 
                              variant="determinate" 
                              value={subnet.utilization} 
                              sx={{ flexGrow: 1, height: 6 }}
                              color={subnet.utilization > 80 ? 'error' : subnet.utilization > 60 ? 'warning' : 'primary'}
                            />
                            <Typography variant="body2">
                              {subnet.utilization}%
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => handleEditSubnet(subnet)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDeleteSubnet(subnet.id)}>
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No IP subnets configured. Click "Add Subnet" to get started.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>DHCP Pools Summary</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {ipSubnets.filter(subnet => subnet.dhcp_enabled).length}
                    </Typography>
                    <Typography variant="body2">Active DHCP Pools</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="text.secondary">
                      {ipSubnets.filter(subnet => !subnet.dhcp_enabled).length}
                    </Typography>
                    <Typography variant="body2">Static Only</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>IP Allocation Summary</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="primary.main">
                      {ipSubnets.length}
                    </Typography>
                    <Typography variant="body2">Total Subnets</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="warning.main">
                      {Math.round(ipSubnets.reduce((avg, subnet) => avg + subnet.utilization, 0) / (ipSubnets.length || 1))}%
                    </Typography>
                    <Typography variant="body2">Avg Utilization</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Subnet Types:
              </Typography>
              <Grid container spacing={1}>
                <Grid item>
                  <Chip 
                    label={`Customer: ${ipSubnets.filter(s => s.type === 'customer').length}`}
                    size="small"
                    color="primary"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`Management: ${ipSubnets.filter(s => s.type === 'management').length}`}
                    size="small"
                    color="warning"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`Infrastructure: ${ipSubnets.filter(s => s.type === 'infrastructure').length}`}
                    size="small"
                    color="default"
                  />
                </Grid>
              </Grid>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderSitesManagement = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Network Sites</Typography>
              <Button 
                startIcon={<Add />} 
                variant="contained"
                onClick={() => setSiteDialogOpen(true)}
              >
                Add Site
              </Button>
            </Box>
            <Box sx={{ mb: 2 }}>
              <TextField
                placeholder="Search sites..."
                variant="outlined"
                size="small"
                InputProps={{
                  startAdornment: <Search />
                }}
              />
            </Box>
            <Grid container spacing={2}>
              {networkSites.length > 0 ? networkSites.map((site) => (
                <Grid item xs={12} md={6} lg={4} key={site.id}>
                  <Card variant="outlined">
                    <CardContent>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="h6">{site.name}</Typography>
                        <Chip 
                          label={site.status} 
                          color={getStatusColor(site.status)}
                          size="small"
                        />
                      </Box>
                      <Typography color="text.secondary" gutterBottom>
                        {site.address}, {site.city}, {site.state} {site.zip_code}
                      </Typography>
                      <Chip 
                        label={site.type.replace('_', ' ').toUpperCase()} 
                        size="small" 
                        variant="outlined"
                        sx={{ mb: 2 }}
                      />
                      {site.contact_name && (
                        <Typography variant="body2" color="text.secondary">
                          Contact: {site.contact_name}
                          {site.contact_phone && ` (${site.contact_phone})`}
                        </Typography>
                      )}
                      {site.coordinates && (
                        <Typography variant="caption" color="text.secondary">
                          Coordinates: {site.coordinates.lat.toFixed(4)}, {site.coordinates.lng.toFixed(4)}
                        </Typography>
                      )}
                      <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
                        <Button 
                          size="small" 
                          startIcon={<Edit />}
                          onClick={() => handleEditSite(site)}
                        >
                          Edit
                        </Button>
                        <Button 
                          size="small" 
                          startIcon={<NetworkCheck />}
                          onClick={() => handleSiteChange(site.id)}
                        >
                          Topology
                        </Button>
                        <IconButton 
                          size="small" 
                          onClick={() => handleDeleteSite(site.id)}
                          color="error"
                        >
                          <Delete />
                        </IconButton>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              )) : (
                <Grid item xs={12}>
                  <Box sx={{ textAlign: 'center', py: 8 }}>
                    <Typography color="text.secondary" variant="h6" gutterBottom>
                      No network sites configured
                    </Typography>
                    <Typography color="text.secondary">
                      Click "Add Site" to create your first network site
                    </Typography>
                  </Box>
                </Grid>
              )}
            </Grid>
          </CardContent>
        </Card>
      </Grid>
      
      {/* Site Statistics */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Site Summary</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="primary.main">
                      {networkSites.length}
                    </Typography>
                    <Typography variant="body2">Total Sites</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {networkSites.filter(site => site.status === 'active').length}
                    </Typography>
                    <Typography variant="body2">Active Sites</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Site Types:
              </Typography>
              <Grid container spacing={1}>
                <Grid item>
                  <Chip 
                    label={`Datacenter: ${networkSites.filter(s => s.type === 'datacenter').length}`}
                    size="small"
                    color="primary"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`POP: ${networkSites.filter(s => s.type === 'pop').length}`}
                    size="small"
                    color="secondary"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`Tower: ${networkSites.filter(s => s.type === 'tower').length}`}
                    size="small"
                    color="info"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`Customer: ${networkSites.filter(s => s.type === 'customer_premises').length}`}
                    size="small"
                    color="default"
                  />
                </Grid>
              </Grid>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Site Status</Typography>
            <Grid container spacing={2}>
              <Grid item xs={4}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {networkSites.filter(site => site.status === 'active').length}
                    </Typography>
                    <Typography variant="body2">Active</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={4}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="warning.main">
                      {networkSites.filter(site => site.status === 'maintenance').length}
                    </Typography>
                    <Typography variant="body2">Maintenance</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={4}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="error.main">
                      {networkSites.filter(site => site.status === 'inactive').length}
                    </Typography>
                    <Typography variant="body2">Inactive</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderEquipmentInventory = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Equipment Inventory</Typography>
              <Button 
                startIcon={<Add />} 
                variant="contained"
                onClick={() => setEquipmentDialogOpen(true)}
              >
                Add Equipment
              </Button>
            </Box>
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Equipment Name</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Manufacturer</TableCell>
                    <TableCell>Model</TableCell>
                    <TableCell>Serial Number</TableCell>
                    <TableCell>Site</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {equipmentList.length > 0 ? (
                    equipmentList.map((equipment) => (
                      <TableRow key={equipment.id}>
                        <TableCell>{equipment.name}</TableCell>
                        <TableCell>
                          <Chip
                            label={equipment.type}
                            size="small"
                            color={equipment.type === 'router' ? 'primary' : 
                                   equipment.type === 'switch' ? 'secondary' : 
                                   equipment.type === 'server' ? 'info' : 'default'}
                          />
                        </TableCell>
                        <TableCell>{equipment.manufacturer}</TableCell>
                        <TableCell>{equipment.model}</TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            {equipment.serial_number}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          {networkSites.find(site => site.id === equipment.site_id)?.name || 'Unknown Site'}
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={equipment.status}
                            size="small"
                            color={getStatusColor(equipment.status)}
                            icon={getStatusIcon(equipment.status)}
                          />
                        </TableCell>
                        <TableCell>
                          <IconButton
                            size="small"
                            onClick={() => handleEditEquipment(equipment)}
                            sx={{ mr: 1 }}
                          >
                            <Edit />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => handleDeleteEquipment(equipment.id)}
                            color="error"
                          >
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No equipment found. Click "Add Equipment" to get started.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Equipment Summary</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="primary.main">
                      {equipmentList.length}
                    </Typography>
                    <Typography variant="body2">Total Equipment</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {equipmentList.filter(eq => eq.status === 'active').length}
                    </Typography>
                    <Typography variant="body2">Active</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Status Distribution:
              </Typography>
              <Grid container spacing={1}>
                <Grid item>
                  <Chip 
                    label={`Active: ${equipmentList.filter(eq => eq.status === 'active').length}`}
                    size="small"
                    color="success"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`Maintenance: ${equipmentList.filter(eq => eq.status === 'maintenance').length}`}
                    size="small"
                    color="warning"
                  />
                </Grid>
                <Grid item>
                  <Chip 
                    label={`Retired: ${equipmentList.filter(eq => eq.status === 'retired').length}`}
                    size="small"
                    color="error"
                  />
                </Grid>
              </Grid>
            </Box>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Equipment by Type</Typography>
            {equipmentList.length > 0 ? (
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Typography variant="h4" color="primary.main">
                        {equipmentList.filter(eq => eq.type === 'router').length}
                      </Typography>
                      <Typography variant="body2">Routers</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Typography variant="h4" color="secondary.main">
                        {equipmentList.filter(eq => eq.type === 'switch').length}
                      </Typography>
                      <Typography variant="body2">Switches</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Typography variant="h4" color="info.main">
                        {equipmentList.filter(eq => eq.type === 'server').length}
                      </Typography>
                      <Typography variant="body2">Servers</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Typography variant="h4" color="warning.main">
                        {equipmentList.filter(eq => eq.type === 'firewall').length}
                      </Typography>
                      <Typography variant="body2">Firewalls</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            ) : (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography color="text.secondary">
                  No equipment to categorize
                </Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderFiberManagement = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Fiber Connections</Typography>
              <Button 
                startIcon={<Add />} 
                variant="contained"
                onClick={() => setFiberDialogOpen(true)}
              >
                Add Connection
              </Button>
            </Box>
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Connection Name</TableCell>
                    <TableCell>From Site</TableCell>
                    <TableCell>To Site</TableCell>
                    <TableCell>Fiber Type</TableCell>
                    <TableCell>Length (km)</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {fiberConnections.length > 0 ? (
                    fiberConnections.map((connection) => (
                      <TableRow key={connection.id}>
                        <TableCell>{connection.connection_name}</TableCell>
                        <TableCell>
                          {networkSites.find(site => site.id === connection.from_site_id)?.name || 'Unknown Site'}
                        </TableCell>
                        <TableCell>
                          {networkSites.find(site => site.id === connection.to_site_id)?.name || 'Unknown Site'}
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={connection.fiber_type.replace('_', ' ').toUpperCase()}
                            size="small"
                            color={connection.fiber_type === 'single_mode' ? 'primary' : 'secondary'}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 'medium' }}>
                            {connection.length_km} km
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={connection.status}
                            size="small"
                            color={getStatusColor(connection.status)}
                            icon={getStatusIcon(connection.status)}
                          />
                        </TableCell>
                        <TableCell>
                          <IconButton
                            size="small"
                            onClick={() => handleEditFiber(connection)}
                            sx={{ mr: 1 }}
                          >
                            <Edit />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => handleDeleteFiber(connection.id)}
                            color="error"
                          >
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={7} sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No fiber connections configured. Click "Add Connection" to get started.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Fiber Statistics</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="primary.main">
                      {fiberConnections.length}
                    </Typography>
                    <Typography variant="body2">Total Connections</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {fiberConnections.filter(conn => conn.status === 'active').length}
                    </Typography>
                    <Typography variant="body2">Active</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Total Length:
              </Typography>
              <Typography variant="h6" color="info.main">
                {fiberConnections.reduce((total, conn) => total + conn.length_km, 0).toFixed(1)} km
              </Typography>
            </Box>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Fiber Type Distribution</Typography>
            {fiberConnections.length > 0 ? (
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Typography variant="h4" color="primary.main">
                        {fiberConnections.filter(conn => conn.fiber_type === 'single_mode').length}
                      </Typography>
                      <Typography variant="body2">Single Mode</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ textAlign: 'center' }}>
                      <Typography variant="h4" color="secondary.main">
                        {fiberConnections.filter(conn => conn.fiber_type === 'multi_mode').length}
                      </Typography>
                      <Typography variant="body2">Multi Mode</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            ) : (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography color="text.secondary">
                  No fiber connections to analyze
                </Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderContent = () => {
    const route = getCurrentRoute();
    
    switch (route) {
      case 'olt-management':
        return renderOLTManagement();
      case 'ip-management':
        return renderIPManagement();
      case 'sites':
        return renderSitesManagement();
      case 'equipment':
        return renderEquipmentInventory();
      case 'fiber-management':
        return renderFiberManagement();
      default:
        return renderNetworkTopology();
    }
  };

  const renderNetworkTopology = () => (
    <>
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
            <FormControl sx={{ minWidth: 200 }}>
              <InputLabel>Select Site</InputLabel>
              <Select
                value={selectedSite}
                onChange={(e) => handleSiteChange(e.target.value as number)}
                label="Select Site"
              >
                {sites.map((site) => (
                  <MenuItem key={site.id} value={site.id}>
                    {site.name} - {site.location}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            
            {selectedSite && (
              <IconButton onClick={() => fetchTopologyData(selectedSite as number)}>
                <Refresh />
              </IconButton>
            )}
          </Box>

          {sites.length > 0 && (
            <Grid container spacing={2}>
              {sites.map((site) => (
                <Grid item xs={12} md={6} lg={4} key={site.id}>
                  <Card 
                    sx={{ 
                      cursor: 'pointer',
                      '&:hover': { backgroundColor: 'action.hover' },
                      border: selectedSite === site.id ? 2 : 1,
                      borderColor: selectedSite === site.id ? 'primary.main' : 'divider'
                    }}
                    onClick={() => handleSiteChange(site.id)}
                  >
                    <CardContent>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="h6">{site.name}</Typography>
                        <Chip 
                          label={site.status} 
                          color={getStatusColor(site.status)}
                          size="small"
                        />
                      </Box>
                      <Typography color="text.secondary" gutterBottom>
                        {site.location}
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <RouterIcon fontSize="small" />
                          <Typography variant="body2">{site.routers} Routers</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Computer fontSize="small" />
                          <Typography variant="body2">{site.customers} Customers</Typography>
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </CardContent>
      </Card>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress />
        </Box>
      )}

      {topologyData && !loading && (
        <Grid container spacing={3}>
          {/* Site Information */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h5" gutterBottom>
                  {topologyData.site.name}
                </Typography>
                <Typography color="text.secondary">
                  Location: {topologyData.site.location}
                </Typography>
                {topologyData.site.coordinates && (
                  <Typography variant="body2" color="text.secondary">
                    Coordinates: {topologyData.site.coordinates.lat}, {topologyData.site.coordinates.lng}
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Routers */}
          <Grid item xs={12} lg={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <RouterIcon />
                  Routers ({topologyData.routers.length})
                </Typography>
                <Grid container spacing={2}>
                  {topologyData.routers.length > 0 ? topologyData.routers.map((router) => (
                    <Grid item xs={12} key={router.id}>
                      <Card 
                        variant="outlined"
                        sx={{ 
                          cursor: 'pointer',
                          '&:hover': { backgroundColor: 'action.hover' }
                        }}
                        onClick={() => handleRouterClick(router)}
                      >
                        <CardContent sx={{ py: 2 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Box>
                              <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                {getStatusIcon(router.status)}
                                {router.name}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                {router.model} - {router.ip_address}
                              </Typography>
                            </Box>
                            <Box sx={{ textAlign: 'right' }}>
                              {router.cpu_usage && (
                                <Typography variant="body2">
                                  CPU: {router.cpu_usage}%
                                </Typography>
                              )}
                              {router.memory_usage && (
                                <Typography variant="body2">
                                  RAM: {router.memory_usage}%
                                </Typography>
                              )}
                            </Box>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  )) : (
                    <Grid item xs={12}>
                      <Box sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No routers found for this site
                        </Typography>
                      </Box>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Equipment */}
          <Grid item xs={12} lg={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Hub />
                  Equipment ({topologyData.equipment.length})
                </Typography>
                <Grid container spacing={1}>
                  {topologyData.equipment.length > 0 ? topologyData.equipment.map((eq) => (
                    <Grid item xs={12} key={eq.id}>
                      <Card variant="outlined">
                        <CardContent sx={{ py: 1.5 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Box>
                              <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                {getStatusIcon(eq.status)}
                                {eq.name}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                {eq.type} - {eq.model}
                              </Typography>
                            </Box>
                            <Chip label={eq.type} size="small" variant="outlined" />
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  )) : (
                    <Grid item xs={12}>
                      <Box sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No equipment found for this site
                        </Typography>
                      </Box>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Subnets */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Cable />
                  IP Subnets ({topologyData.subnets.length})
                </Typography>
                <Grid container spacing={2}>
                  {topologyData.subnets.length > 0 ? topologyData.subnets.map((subnet) => (
                    <Grid item xs={12} md={6} lg={4} key={subnet.id}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle1" gutterBottom>
                            {subnet.name}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            Network: {subnet.network}
                          </Typography>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
                            <Chip 
                              label={`VLAN ${subnet.vlan_id}`} 
                              size="small" 
                              color="primary" 
                              variant="outlined"
                            />
                            <Typography variant="body2">
                              {subnet.assignments} assignments
                            </Typography>
                          </Box>
                          <Chip 
                            label={subnet.type} 
                            size="small" 
                            sx={{ mt: 1 }}
                          />
                        </CardContent>
                      </Card>
                    </Grid>
                  )) : (
                    <Grid item xs={12}>
                      <Box sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No subnets configured for this site
                        </Typography>
                      </Box>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Router Details Dialog */}
      <Dialog 
        open={routerDialogOpen} 
        onClose={() => setRouterDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RouterIcon />
          {selectedRouter?.name} Details
        </DialogTitle>
        <DialogContent>
          {selectedRouter && (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Router Information</Typography>
                <List>
                  <ListItem>
                    <ListItemText 
                      primary="Status" 
                      secondary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          {getStatusIcon(selectedRouter.status)}
                          {selectedRouter.status}
                        </Box>
                      }
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="Model" secondary={selectedRouter.model} />
                  </ListItem>
                  <ListItem>
                    <ListItemText primary="IP Address" secondary={selectedRouter.ip_address} />
                  </ListItem>
                  {selectedRouter.uptime && (
                    <ListItem>
                      <ListItemText primary="Uptime" secondary={selectedRouter.uptime} />
                    </ListItem>
                  )}
                </List>
              </Grid>

              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Performance</Typography>
                <List>
                  {selectedRouter.cpu_usage && (
                    <ListItem>
                      <ListItemIcon><Memory /></ListItemIcon>
                      <ListItemText 
                        primary="CPU Usage" 
                        secondary={`${selectedRouter.cpu_usage}%`}
                      />
                    </ListItem>
                  )}
                  {selectedRouter.memory_usage && (
                    <ListItem>
                      <ListItemIcon><Memory /></ListItemIcon>
                      <ListItemText 
                        primary="Memory Usage" 
                        secondary={`${selectedRouter.memory_usage}%`}
                      />
                    </ListItem>
                  )}
                </List>
              </Grid>

              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom>Network Interfaces</Typography>
                <Grid container spacing={1}>
                  {selectedRouter.interfaces.map((iface, index) => (
                    <Grid item xs={12} sm={6} md={4} key={index}>
                      <Card variant="outlined">
                        <CardContent sx={{ py: 1.5 }}>
                          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {getStatusIcon(iface.status)}
                            {iface.name}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {iface.ip || 'No IP assigned'}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </Grid>
            </Grid>
          )}
        </DialogContent>
      </Dialog>
    </>
  );

  return (
    <Box sx={{ p: 3 }}>
      {(() => {
        const config = getRouteConfig();
        return (
          <Box sx={{ mb: 3 }}>
            <Typography variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {config.icon}
              {config.title}
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
              {config.description}
            </Typography>
          </Box>
        );
      })()}

      {renderContent()}

      {/* OLT Device Dialog */}
      <Dialog open={oltDialogOpen} onClose={() => {setOltDialogOpen(false); resetOLTForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedOlt ? 'Edit OLT Device' : 'Add OLT Device'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Device Name"
                value={oltForm.name}
                onChange={(e) => setOltForm({ ...oltForm, name: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="IP Address"
                value={oltForm.ip_address}
                onChange={(e) => setOltForm({ ...oltForm, ip_address: e.target.value })}
                placeholder="192.168.1.100"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Model"
                value={oltForm.model}
                onChange={(e) => setOltForm({ ...oltForm, model: e.target.value })}
                placeholder="e.g., Huawei MA5800-X17"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Firmware Version"
                value={oltForm.firmware_version}
                onChange={(e) => setOltForm({ ...oltForm, firmware_version: e.target.value })}
                placeholder="e.g., V800R021C00"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Serial Number"
                value={oltForm.serial_number}
                onChange={(e) => setOltForm({ ...oltForm, serial_number: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Max ONUs"
                value={oltForm.max_onus}
                onChange={(e) => setOltForm({ ...oltForm, max_onus: parseInt(e.target.value) || 32 })}
                inputProps={{ min: 1, max: 1024 }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Location"
                value={oltForm.location}
                onChange={(e) => setOltForm({ ...oltForm, location: e.target.value })}
                placeholder="e.g., Rack 1, Site A"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={oltForm.status}
                  onChange={(e) => setOltForm({ ...oltForm, status: e.target.value as any })}
                  label="Status"
                >
                  <MenuItem value="online">Online</MenuItem>
                  <MenuItem value="offline">Offline</MenuItem>
                  <MenuItem value="maintenance">Maintenance</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setOltDialogOpen(false); resetOLTForm();}}>Cancel</Button>
          <Button onClick={handleCreateOLT} variant="contained">
            {selectedOlt ? 'Update' : 'Create'} OLT Device
          </Button>
        </DialogActions>
      </Dialog>

      {/* IP Subnet Dialog */}
      <Dialog open={subnetDialogOpen} onClose={() => {setSubnetDialogOpen(false); resetSubnetForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedSubnet ? 'Edit IP Subnet' : 'Add IP Subnet'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Subnet Name"
                value={subnetForm.name}
                onChange={(e) => setSubnetForm({ ...subnetForm, name: e.target.value })}
                placeholder="e.g., Customer VLAN 100"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Network Address"
                value={subnetForm.network}
                onChange={(e) => setSubnetForm({ ...subnetForm, network: e.target.value })}
                placeholder="192.168.1.0"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Subnet Mask"
                value={subnetForm.mask}
                onChange={(e) => setSubnetForm({ ...subnetForm, mask: e.target.value })}
                placeholder="255.255.255.0 or /24"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Gateway"
                value={subnetForm.gateway}
                onChange={(e) => setSubnetForm({ ...subnetForm, gateway: e.target.value })}
                placeholder="192.168.1.1"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="VLAN ID"
                value={subnetForm.vlan_id}
                onChange={(e) => setSubnetForm({ ...subnetForm, vlan_id: parseInt(e.target.value) || 1 })}
                inputProps={{ min: 1, max: 4094 }}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Subnet Type</InputLabel>
                <Select
                  value={subnetForm.type}
                  onChange={(e) => setSubnetForm({ ...subnetForm, type: e.target.value as any })}
                  label="Subnet Type"
                >
                  <MenuItem value="customer">Customer</MenuItem>
                  <MenuItem value="management">Management</MenuItem>
                  <MenuItem value="infrastructure">Infrastructure</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={subnetForm.dhcp_enabled}
                    onChange={(e) => setSubnetForm({ ...subnetForm, dhcp_enabled: e.target.checked })}
                  />
                }
                label="Enable DHCP Server"
              />
            </Grid>
            {subnetForm.dhcp_enabled && (
              <>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="DHCP Range Start"
                    value={subnetForm.dhcp_range_start}
                    onChange={(e) => setSubnetForm({ ...subnetForm, dhcp_range_start: e.target.value })}
                    placeholder="192.168.1.100"
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="DHCP Range End"
                    value={subnetForm.dhcp_range_end}
                    onChange={(e) => setSubnetForm({ ...subnetForm, dhcp_range_end: e.target.value })}
                    placeholder="192.168.1.200"
                  />
                </Grid>
              </>
            )}
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Associated Site</InputLabel>
                <Select
                  value={subnetForm.site_id}
                  onChange={(e) => setSubnetForm({ ...subnetForm, site_id: e.target.value })}
                  label="Associated Site"
                >
                  <MenuItem value="">None</MenuItem>
                  {sites.map((site) => (
                    <MenuItem key={site.id} value={site.id}>
                      {site.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setSubnetDialogOpen(false); resetSubnetForm();}}>Cancel</Button>
          <Button onClick={handleCreateSubnet} variant="contained">
            {selectedSubnet ? 'Update' : 'Create'} Subnet
          </Button>
        </DialogActions>
      </Dialog>

      {/* Site Dialog */}
      <Dialog open={siteDialogOpen} onClose={() => {setSiteDialogOpen(false); resetSiteForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedNetworkSite ? 'Edit Network Site' : 'Add Network Site'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Site Name"
                value={siteForm.name}
                onChange={(e) => setSiteForm({ ...siteForm, name: e.target.value })}
                placeholder="e.g., Main Datacenter"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Site Type</InputLabel>
                <Select
                  value={siteForm.type}
                  onChange={(e) => setSiteForm({ ...siteForm, type: e.target.value as any })}
                  label="Site Type"
                >
                  <MenuItem value="datacenter">Datacenter</MenuItem>
                  <MenuItem value="pop">Point of Presence (POP)</MenuItem>
                  <MenuItem value="customer_premises">Customer Premises</MenuItem>
                  <MenuItem value="tower">Tower Site</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Address"
                value={siteForm.address}
                onChange={(e) => setSiteForm({ ...siteForm, address: e.target.value })}
                placeholder="123 Main Street"
                required
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="City"
                value={siteForm.city}
                onChange={(e) => setSiteForm({ ...siteForm, city: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="State/Province"
                value={siteForm.state}
                onChange={(e) => setSiteForm({ ...siteForm, state: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="ZIP/Postal Code"
                value={siteForm.zip_code}
                onChange={(e) => setSiteForm({ ...siteForm, zip_code: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Latitude"
                value={siteForm.coordinates_lat}
                onChange={(e) => setSiteForm({ ...siteForm, coordinates_lat: e.target.value })}
                placeholder="40.7128"
                inputProps={{ step: 'any' }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Longitude"
                value={siteForm.coordinates_lng}
                onChange={(e) => setSiteForm({ ...siteForm, coordinates_lng: e.target.value })}
                placeholder="-74.0060"
                inputProps={{ step: 'any' }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Contact Name"
                value={siteForm.contact_name}
                onChange={(e) => setSiteForm({ ...siteForm, contact_name: e.target.value })}
                placeholder="Site Manager Name"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Contact Phone"
                value={siteForm.contact_phone}
                onChange={(e) => setSiteForm({ ...siteForm, contact_phone: e.target.value })}
                placeholder="+1 (555) 123-4567"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={siteForm.status}
                  onChange={(e) => setSiteForm({ ...siteForm, status: e.target.value as any })}
                  label="Status"
                >
                  <MenuItem value="active">Active</MenuItem>
                  <MenuItem value="inactive">Inactive</MenuItem>
                  <MenuItem value="maintenance">Maintenance</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setSiteDialogOpen(false); resetSiteForm();}}>Cancel</Button>
          <Button onClick={handleCreateSite} variant="contained">
            {selectedNetworkSite ? 'Update' : 'Create'} Site
          </Button>
        </DialogActions>
      </Dialog>

      {/* Equipment Dialog */}
      <Dialog open={equipmentDialogOpen} onClose={() => {setEquipmentDialogOpen(false); resetEquipmentForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedEquipment ? 'Edit Equipment' : 'Add Equipment'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Equipment Name"
                value={equipmentForm.name}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, name: e.target.value })}
                placeholder="e.g., Core Router 1"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth required>
                <InputLabel>Equipment Type</InputLabel>
                <Select
                  value={equipmentForm.type}
                  onChange={(e) => setEquipmentForm({ ...equipmentForm, type: e.target.value as any })}
                  label="Equipment Type"
                >
                  <MenuItem value="router">Router</MenuItem>
                  <MenuItem value="switch">Switch</MenuItem>
                  <MenuItem value="server">Server</MenuItem>
                  <MenuItem value="firewall">Firewall</MenuItem>
                  <MenuItem value="access_point">Access Point</MenuItem>
                  <MenuItem value="load_balancer">Load Balancer</MenuItem>
                  <MenuItem value="storage">Storage</MenuItem>
                  <MenuItem value="other">Other</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Manufacturer"
                value={equipmentForm.manufacturer}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, manufacturer: e.target.value })}
                placeholder="e.g., Cisco, Juniper, Dell"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Model"
                value={equipmentForm.model}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, model: e.target.value })}
                placeholder="e.g., ASR1001-X"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Serial Number"
                value={equipmentForm.serial_number}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, serial_number: e.target.value })}
                placeholder="Equipment serial number"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Asset Tag"
                value={equipmentForm.asset_tag}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, asset_tag: e.target.value })}
                placeholder="Internal asset tag"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Site Location</InputLabel>
                <Select
                  value={equipmentForm.site_id}
                  onChange={(e) => setEquipmentForm({ ...equipmentForm, site_id: e.target.value })}
                  label="Site Location"
                >
                  <MenuItem value="">No Site Assigned</MenuItem>
                  {networkSites.map((site) => (
                    <MenuItem key={site.id} value={site.id.toString()}>
                      {site.name} ({site.type})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Rack Location"
                value={equipmentForm.rack_location}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, rack_location: e.target.value })}
                placeholder="e.g., Rack 1, U12-14"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={equipmentForm.status}
                  onChange={(e) => setEquipmentForm({ ...equipmentForm, status: e.target.value as any })}
                  label="Status"
                >
                  <MenuItem value="active">Active</MenuItem>
                  <MenuItem value="inactive">Inactive</MenuItem>
                  <MenuItem value="maintenance">Maintenance</MenuItem>
                  <MenuItem value="retired">Retired</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="date"
                label="Purchase Date"
                value={equipmentForm.purchase_date}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, purchase_date: e.target.value })}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="date"
                label="Warranty Expiry"
                value={equipmentForm.warranty_expiry}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, warranty_expiry: e.target.value })}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                rows={3}
                label="Notes"
                value={equipmentForm.notes}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, notes: e.target.value })}
                placeholder="Additional notes about this equipment..."
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setEquipmentDialogOpen(false); resetEquipmentForm();}}>Cancel</Button>
          <Button onClick={handleCreateEquipment} variant="contained">
            {selectedEquipment ? 'Update' : 'Create'} Equipment
          </Button>
        </DialogActions>
      </Dialog>

      {/* Fiber Connection Dialog */}
      <Dialog open={fiberDialogOpen} onClose={() => {setFiberDialogOpen(false); resetFiberForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedFiber ? 'Edit Fiber Connection' : 'Add Fiber Connection'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Connection Name"
                value={fiberForm.connection_name}
                onChange={(e) => setFiberForm({ ...fiberForm, connection_name: e.target.value })}
                placeholder="e.g., Site A to Site B Primary"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth required>
                <InputLabel>From Site</InputLabel>
                <Select
                  value={fiberForm.from_site_id}
                  onChange={(e) => setFiberForm({ ...fiberForm, from_site_id: e.target.value })}
                  label="From Site"
                >
                  {networkSites.map((site) => (
                    <MenuItem key={site.id} value={site.id.toString()}>
                      {site.name} ({site.type})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth required>
                <InputLabel>To Site</InputLabel>
                <Select
                  value={fiberForm.to_site_id}
                  onChange={(e) => setFiberForm({ ...fiberForm, to_site_id: e.target.value })}
                  label="To Site"
                >
                  {networkSites.map((site) => (
                    <MenuItem key={site.id} value={site.id.toString()}>
                      {site.name} ({site.type})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="From Equipment"
                value={fiberForm.from_equipment}
                onChange={(e) => setFiberForm({ ...fiberForm, from_equipment: e.target.value })}
                placeholder="e.g., OLT Port 1/1/1"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="To Equipment"
                value={fiberForm.to_equipment}
                onChange={(e) => setFiberForm({ ...fiberForm, to_equipment: e.target.value })}
                placeholder="e.g., ODF Panel A Port 12"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth required>
                <InputLabel>Fiber Type</InputLabel>
                <Select
                  value={fiberForm.fiber_type}
                  onChange={(e) => setFiberForm({ ...fiberForm, fiber_type: e.target.value as any })}
                  label="Fiber Type"
                >
                  <MenuItem value="single_mode">Single Mode</MenuItem>
                  <MenuItem value="multi_mode">Multi Mode</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Fiber Count"
                value={fiberForm.fiber_count}
                onChange={(e) => setFiberForm({ ...fiberForm, fiber_count: parseInt(e.target.value) || 1 })}
                inputProps={{ min: 1, max: 288 }}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Length (km)"
                value={fiberForm.length_km}
                onChange={(e) => setFiberForm({ ...fiberForm, length_km: parseFloat(e.target.value) || 0 })}
                inputProps={{ min: 0, step: 0.1 }}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={fiberForm.status}
                  onChange={(e) => setFiberForm({ ...fiberForm, status: e.target.value as any })}
                  label="Status"
                >
                  <MenuItem value="active">Active</MenuItem>
                  <MenuItem value="inactive">Inactive</MenuItem>
                  <MenuItem value="maintenance">Maintenance</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Service Provider"
                value={fiberForm.provider}
                onChange={(e) => setFiberForm({ ...fiberForm, provider: e.target.value })}
                placeholder="e.g., Zayo, Crown Castle"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Circuit ID"
                value={fiberForm.circuit_id}
                onChange={(e) => setFiberForm({ ...fiberForm, circuit_id: e.target.value })}
                placeholder="Provider circuit identifier"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="date"
                label="Installation Date"
                value={fiberForm.installation_date}
                onChange={(e) => setFiberForm({ ...fiberForm, installation_date: e.target.value })}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                rows={3}
                label="Notes"
                value={fiberForm.notes}
                onChange={(e) => setFiberForm({ ...fiberForm, notes: e.target.value })}
                placeholder="Additional notes about this fiber connection..."
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setFiberDialogOpen(false); resetFiberForm();}}>Cancel</Button>
          <Button onClick={handleCreateFiber} variant="contained">
            {selectedFiber ? 'Update' : 'Create'} Connection
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default NetworkTopology;