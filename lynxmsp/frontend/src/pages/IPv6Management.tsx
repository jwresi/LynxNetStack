import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  CardActions,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  Alert,
  Tooltip,
  LinearProgress,
  Badge,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Refresh,
  ExpandMore,
  Visibility,
  Security,
  Router as RouterIcon,
  Cable,
  Timeline,
  MonitorHeart,
  DeviceHub,
  Assignment,
  Settings,
  Warning,
  CheckCircle,
  Error as ErrorIcon,
  VpnKey,
  Storage,
  Public,
  Share,
  Shield,
  Speed
} from '@mui/icons-material';
import api from '../services/api';

// IPv6 Address Management Interfaces
interface IPv6Subnet {
  id: number;
  subnet: string;
  prefix_length: number;
  allocation_type: 'customer' | 'infrastructure' | 'pool';
  status: 'active' | 'reserved' | 'deprecated';
  description?: string;
  vlan_id?: number;
  site_id?: number;
  delegated_length?: number;
  created_at: string;
  updated_at: string;
}

interface IPv6Address {
  id: number;
  address: string;
  subnet_id: number;
  customer_id?: number;
  device_id?: number;
  interface_name?: string;
  address_type: 'static' | 'dhcpv6' | 'slaac' | 'link-local';
  status: 'active' | 'reserved' | 'deprecated';
  description?: string;
  created_at: string;
}

interface IPv6Route {
  id: number;
  destination: string;
  prefix_length: number;
  next_hop: string;
  interface?: string;
  metric: number;
  route_type: 'static' | 'dynamic' | 'default';
  status: 'active' | 'inactive';
  description?: string;
  created_at: string;
}

interface IPv6FirewallRule {
  id: number;
  name: string;
  source: string;
  destination: string;
  protocol: 'tcp' | 'udp' | 'icmpv6' | 'any';
  source_port?: string;
  destination_port?: string;
  action: 'allow' | 'deny' | 'drop';
  priority: number;
  enabled: boolean;
  description?: string;
  created_at: string;
}

interface IPv6Monitoring {
  connectivity_test: {
    status: 'success' | 'failure' | 'warning';
    latency: number;
    packet_loss: number;
    last_test: string;
  };
  neighbor_discovery: {
    active_neighbors: number;
    neighbor_cache_size: number;
    duplicate_address_detection: boolean;
  };
  dhcpv6_stats: {
    active_leases: number;
    pool_utilization: number;
    requests_per_hour: number;
  };
  traffic_stats: {
    bytes_in: number;
    bytes_out: number;
    packets_in: number;
    packets_out: number;
    errors: number;
  };
}

const IPv6Management: React.FC = () => {
  // State management
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Data states
  const [subnets, setSubnets] = useState<IPv6Subnet[]>([]);
  const [addresses, setAddresses] = useState<IPv6Address[]>([]);
  const [routes, setRoutes] = useState<IPv6Route[]>([]);
  const [firewallRules, setFirewallRules] = useState<IPv6FirewallRule[]>([]);
  const [monitoring, setMonitoring] = useState<IPv6Monitoring | null>(null);

  // Dialog states
  const [subnetDialogOpen, setSubnetDialogOpen] = useState(false);
  const [addressDialogOpen, setAddressDialogOpen] = useState(false);
  const [routeDialogOpen, setRouteDialogOpen] = useState(false);
  const [firewallDialogOpen, setFirewallDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{type: string, id: number, name: string} | null>(null);

  // Form states
  const [selectedSubnet, setSelectedSubnet] = useState<IPv6Subnet | null>(null);
  const [selectedAddress, setSelectedAddress] = useState<IPv6Address | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<IPv6Route | null>(null);
  const [selectedFirewallRule, setSelectedFirewallRule] = useState<IPv6FirewallRule | null>(null);

  const [subnetForm, setSubnetForm] = useState({
    subnet: '',
    prefix_length: 64,
    allocation_type: 'customer' as const,
    status: 'active' as const,
    description: '',
    vlan_id: '',
    site_id: '',
    delegated_length: 64
  });

  const [addressForm, setAddressForm] = useState({
    address: '',
    subnet_id: '',
    customer_id: '',
    device_id: '',
    interface_name: '',
    address_type: 'static' as const,
    status: 'active' as const,
    description: ''
  });

  const [routeForm, setRouteForm] = useState({
    destination: '',
    prefix_length: 64,
    next_hop: '',
    interface: '',
    metric: 100,
    route_type: 'static' as const,
    status: 'active' as const,
    description: ''
  });

  const [firewallForm, setFirewallForm] = useState({
    name: '',
    source: '',
    destination: '',
    protocol: 'tcp' as const,
    source_port: '',
    destination_port: '',
    action: 'allow' as const,
    priority: 100,
    enabled: true,
    description: ''
  });

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadSubnets(),
        loadAddresses(),
        loadRoutes(),
        loadFirewallRules(),
        loadMonitoring()
      ]);
    } catch (err) {
      setError('Failed to load IPv6 data');
      console.error('Error loading IPv6 data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadSubnets = async () => {
    try {
      const response = await api.get('/api/v1/ipv6/subnets');
      setSubnets(response.data || []);
    } catch (err) {
      console.error('Failed to load IPv6 subnets:', err);
      setSubnets([]);
    }
  };

  const loadAddresses = async () => {
    try {
      const response = await api.get('/api/v1/ipv6/addresses');
      setAddresses(response.data || []);
    } catch (err) {
      console.error('Failed to load IPv6 addresses:', err);
      setAddresses([]);
    }
  };

  const loadRoutes = async () => {
    try {
      const response = await api.get('/api/v1/ipv6/routes');
      setRoutes(response.data || []);
    } catch (err) {
      console.error('Failed to load IPv6 routes:', err);
      setRoutes([]);
    }
  };

  const loadFirewallRules = async () => {
    try {
      const response = await api.get('/api/v1/ipv6/firewall');
      setFirewallRules(response.data || []);
    } catch (err) {
      console.error('Failed to load IPv6 firewall rules:', err);
      setFirewallRules([]);
    }
  };

  const loadMonitoring = async () => {
    try {
      const response = await api.get('/api/v1/ipv6/monitoring');
      setMonitoring(response.data);
    } catch (err) {
      console.error('Failed to load IPv6 monitoring data:', err);
      setMonitoring(null);
    }
  };

  // Subnet Management Functions
  const handleCreateSubnet = async () => {
    try {
      await api.post('/api/v1/ipv6/subnets', {
        ...subnetForm,
        vlan_id: subnetForm.vlan_id ? parseInt(subnetForm.vlan_id) : null,
        site_id: subnetForm.site_id ? parseInt(subnetForm.site_id) : null
      });
      setSubnetDialogOpen(false);
      resetSubnetForm();
      loadSubnets();
    } catch (err) {
      setError('Failed to create IPv6 subnet');
      console.error('Error creating subnet:', err);
    }
  };

  const handleEditSubnet = (subnet: IPv6Subnet) => {
    setSelectedSubnet(subnet);
    setSubnetForm({
      subnet: subnet.subnet,
      prefix_length: subnet.prefix_length,
      allocation_type: subnet.allocation_type as any,
      status: subnet.status as any,
      description: subnet.description || '',
      vlan_id: subnet.vlan_id?.toString() || '',
      site_id: subnet.site_id?.toString() || '',
      delegated_length: subnet.delegated_length || 64
    });
    setSubnetDialogOpen(true);
  };

  const handleDeleteSubnet = (subnet: IPv6Subnet) => {
    setDeleteTarget({
      type: 'subnet',
      id: subnet.id,
      name: `${subnet.subnet}/${subnet.prefix_length}`
    });
    setDeleteDialogOpen(true);
  };

  // Address Management Functions
  const handleCreateAddress = async () => {
    try {
      await api.post('/api/v1/ipv6/addresses', {
        ...addressForm,
        subnet_id: parseInt(addressForm.subnet_id),
        customer_id: addressForm.customer_id ? parseInt(addressForm.customer_id) : null,
        device_id: addressForm.device_id ? parseInt(addressForm.device_id) : null
      });
      setAddressDialogOpen(false);
      resetAddressForm();
      loadAddresses();
    } catch (err) {
      setError('Failed to create IPv6 address');
      console.error('Error creating address:', err);
    }
  };

  const handleEditAddress = (address: IPv6Address) => {
    setSelectedAddress(address);
    setAddressForm({
      address: address.address,
      subnet_id: address.subnet_id.toString(),
      customer_id: address.customer_id?.toString() || '',
      device_id: address.device_id?.toString() || '',
      interface_name: address.interface_name || '',
      address_type: address.address_type as any,
      status: address.status as any,
      description: address.description || ''
    });
    setAddressDialogOpen(true);
  };

  const handleDeleteAddress = (address: IPv6Address) => {
    setDeleteTarget({
      type: 'address',
      id: address.id,
      name: address.address
    });
    setDeleteDialogOpen(true);
  };

  // Route Management Functions
  const handleCreateRoute = async () => {
    try {
      await api.post('/api/v1/ipv6/routes', routeForm);
      setRouteDialogOpen(false);
      resetRouteForm();
      loadRoutes();
    } catch (err) {
      setError('Failed to create IPv6 route');
      console.error('Error creating route:', err);
    }
  };

  const handleEditRoute = (route: IPv6Route) => {
    setSelectedRoute(route);
    setRouteForm({
      destination: route.destination,
      prefix_length: route.prefix_length,
      next_hop: route.next_hop,
      interface: route.interface || '',
      metric: route.metric,
      route_type: route.route_type as any,
      status: route.status as any,
      description: route.description || ''
    });
    setRouteDialogOpen(true);
  };

  const handleDeleteRoute = (route: IPv6Route) => {
    setDeleteTarget({
      type: 'route',
      id: route.id,
      name: `${route.destination}/${route.prefix_length}`
    });
    setDeleteDialogOpen(true);
  };

  // Firewall Rule Management Functions
  const handleCreateFirewallRule = async () => {
    try {
      await api.post('/api/v1/ipv6/firewall', firewallForm);
      setFirewallDialogOpen(false);
      resetFirewallForm();
      loadFirewallRules();
    } catch (err) {
      setError('Failed to create IPv6 firewall rule');
      console.error('Error creating firewall rule:', err);
    }
  };

  const handleEditFirewallRule = (rule: IPv6FirewallRule) => {
    setSelectedFirewallRule(rule);
    setFirewallForm({
      name: rule.name,
      source: rule.source,
      destination: rule.destination,
      protocol: rule.protocol as any,
      source_port: rule.source_port || '',
      destination_port: rule.destination_port || '',
      action: rule.action as any,
      priority: rule.priority,
      enabled: rule.enabled,
      description: rule.description || ''
    });
    setFirewallDialogOpen(true);
  };

  const handleDeleteFirewallRule = (rule: IPv6FirewallRule) => {
    setDeleteTarget({
      type: 'firewall',
      id: rule.id,
      name: rule.name
    });
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    
    setDeleteLoading(true);
    try {
      const endpoints = {
        subnet: `/api/v1/ipv6/subnets/${deleteTarget.id}`,
        address: `/api/v1/ipv6/addresses/${deleteTarget.id}`,
        route: `/api/v1/ipv6/routes/${deleteTarget.id}`,
        firewall: `/api/v1/ipv6/firewall/${deleteTarget.id}`
      };
      
      await api.delete(endpoints[deleteTarget.type as keyof typeof endpoints]);
      
      // Reload appropriate data
      switch (deleteTarget.type) {
        case 'subnet': loadSubnets(); break;
        case 'address': loadAddresses(); break;
        case 'route': loadRoutes(); break;
        case 'firewall': loadFirewallRules(); break;
      }
      
      setDeleteDialogOpen(false);
      setDeleteTarget(null);
    } catch (err) {
      setError(`Failed to delete IPv6 ${deleteTarget.type}`);
      console.error(`Error deleting ${deleteTarget.type}:`, err);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCancelDelete = () => {
    setDeleteDialogOpen(false);
    setDeleteTarget(null);
  };

  // Form reset functions
  const resetSubnetForm = () => {
    setSubnetForm({
      subnet: '',
      prefix_length: 64,
      allocation_type: 'customer',
      status: 'active',
      description: '',
      vlan_id: '',
      site_id: '',
      delegated_length: 64
    });
    setSelectedSubnet(null);
  };

  const resetAddressForm = () => {
    setAddressForm({
      address: '',
      subnet_id: '',
      customer_id: '',
      device_id: '',
      interface_name: '',
      address_type: 'static',
      status: 'active',
      description: ''
    });
    setSelectedAddress(null);
  };

  const resetRouteForm = () => {
    setRouteForm({
      destination: '',
      prefix_length: 64,
      next_hop: '',
      interface: '',
      metric: 100,
      route_type: 'static',
      status: 'active',
      description: ''
    });
    setSelectedRoute(null);
  };

  const resetFirewallForm = () => {
    setFirewallForm({
      name: '',
      source: '',
      destination: '',
      protocol: 'tcp',
      source_port: '',
      destination_port: '',
      action: 'allow',
      priority: 100,
      enabled: true,
      description: ''
    });
    setSelectedFirewallRule(null);
  };

  // Utility functions
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'success';
      case 'reserved': return 'warning';
      case 'deprecated': return 'error';
      case 'inactive': return 'default';
      default: return 'default';
    }
  };

  const getActionColor = (action: string) => {
    switch (action) {
      case 'allow': return 'success';
      case 'deny': return 'warning';
      case 'drop': return 'error';
      default: return 'default';
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">IPv6 Management</Typography>
        <Button
          variant="contained"
          startIcon={<Refresh />}
          onClick={loadInitialData}
          disabled={loading}
        >
          Refresh Data
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {loading && <LinearProgress sx={{ mb: 3 }} />}

      <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <Tab label="Subnets" icon={<Public />} />
        <Tab label="Addresses" icon={<Share />} />
        <Tab label="Routing" icon={<RouterIcon />} />
        <Tab label="Firewall" icon={<Shield />} />
        <Tab label="Monitoring" icon={<MonitorHeart />} />
      </Tabs>

      {/* IPv6 Subnets Tab */}
      {tabValue === 0 && (
        <Box>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6">IPv6 Subnets</Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setSubnetDialogOpen(true)}
            >
              Add Subnet
            </Button>
          </Box>

          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Subnet</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>VLAN</TableCell>
                      <TableCell>Site</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {subnets.map((subnet) => (
                      <TableRow key={subnet.id}>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {subnet.subnet}/{subnet.prefix_length}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={subnet.allocation_type} 
                            size="small" 
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={subnet.status} 
                            size="small" 
                            color={getStatusColor(subnet.status)}
                          />
                        </TableCell>
                        <TableCell>{subnet.vlan_id || 'N/A'}</TableCell>
                        <TableCell>{subnet.site_id || 'N/A'}</TableCell>
                        <TableCell>{subnet.description || 'N/A'}</TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => handleEditSubnet(subnet)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDeleteSubnet(subnet)}>
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* IPv6 Addresses Tab */}
      {tabValue === 1 && (
        <Box>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6">IPv6 Addresses</Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddressDialogOpen(true)}
            >
              Add Address
            </Button>
          </Box>

          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>IPv6 Address</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Customer</TableCell>
                      <TableCell>Device/Interface</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {addresses.map((address) => (
                      <TableRow key={address.id}>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {address.address}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={address.address_type} 
                            size="small" 
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={address.status} 
                            size="small" 
                            color={getStatusColor(address.status)}
                          />
                        </TableCell>
                        <TableCell>{address.customer_id || 'N/A'}</TableCell>
                        <TableCell>
                          {address.device_id && address.interface_name 
                            ? `${address.device_id}/${address.interface_name}`
                            : 'N/A'
                          }
                        </TableCell>
                        <TableCell>{address.description || 'N/A'}</TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => handleEditAddress(address)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDeleteAddress(address)}>
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* IPv6 Routing Tab */}
      {tabValue === 2 && (
        <Box>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6">IPv6 Routes</Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setRouteDialogOpen(true)}
            >
              Add Route
            </Button>
          </Box>

          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Destination</TableCell>
                      <TableCell>Next Hop</TableCell>
                      <TableCell>Interface</TableCell>
                      <TableCell>Metric</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {routes.map((route) => (
                      <TableRow key={route.id}>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {route.destination}/{route.prefix_length}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {route.next_hop}
                          </Typography>
                        </TableCell>
                        <TableCell>{route.interface || 'N/A'}</TableCell>
                        <TableCell>{route.metric}</TableCell>
                        <TableCell>
                          <Chip 
                            label={route.route_type} 
                            size="small" 
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={route.status} 
                            size="small" 
                            color={getStatusColor(route.status)}
                          />
                        </TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => handleEditRoute(route)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDeleteRoute(route)}>
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* IPv6 Firewall Tab */}
      {tabValue === 3 && (
        <Box>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6">IPv6 Firewall Rules</Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setFirewallDialogOpen(true)}
            >
              Add Rule
            </Button>
          </Box>

          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Name</TableCell>
                      <TableCell>Source</TableCell>
                      <TableCell>Destination</TableCell>
                      <TableCell>Protocol/Port</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Priority</TableCell>
                      <TableCell>Enabled</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {firewallRules.map((rule) => (
                      <TableRow key={rule.id}>
                        <TableCell>{rule.name}</TableCell>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {rule.source}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {rule.destination}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          {rule.protocol}
                          {rule.destination_port && `/${rule.destination_port}`}
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={rule.action} 
                            size="small" 
                            color={getActionColor(rule.action)}
                          />
                        </TableCell>
                        <TableCell>{rule.priority}</TableCell>
                        <TableCell>
                          <Chip 
                            label={rule.enabled ? 'Enabled' : 'Disabled'} 
                            size="small" 
                            color={rule.enabled ? 'success' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => handleEditFirewallRule(rule)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDeleteFirewallRule(rule)}>
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* IPv6 Monitoring Tab */}
      {tabValue === 4 && (
        <Box>
          <Typography variant="h6" mb={3}>IPv6 Monitoring & Diagnostics</Typography>
          
          {monitoring && (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Connectivity Test" />
                  <CardContent>
                    <Box display="flex" alignItems="center" mb={2}>
                      {monitoring.connectivity_test.status === 'success' && (
                        <CheckCircle color="success" />
                      )}
                      {monitoring.connectivity_test.status === 'failure' && (
                        <ErrorIcon color="error" />
                      )}
                      {monitoring.connectivity_test.status === 'warning' && (
                        <Warning color="warning" />
                      )}
                      <Typography variant="h6" ml={1}>
                        {monitoring.connectivity_test.status.toUpperCase()}
                      </Typography>
                    </Box>
                    <Typography variant="body2">
                      Latency: {monitoring.connectivity_test.latency}ms
                    </Typography>
                    <Typography variant="body2">
                      Packet Loss: {monitoring.connectivity_test.packet_loss}%
                    </Typography>
                    <Typography variant="body2">
                      Last Test: {new Date(monitoring.connectivity_test.last_test).toLocaleString()}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Neighbor Discovery" />
                  <CardContent>
                    <Typography variant="body2">
                      Active Neighbors: {monitoring.neighbor_discovery.active_neighbors}
                    </Typography>
                    <Typography variant="body2">
                      Cache Size: {monitoring.neighbor_discovery.neighbor_cache_size}
                    </Typography>
                    <Typography variant="body2">
                      DAD Enabled: {monitoring.neighbor_discovery.duplicate_address_detection ? 'Yes' : 'No'}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="DHCPv6 Statistics" />
                  <CardContent>
                    <Typography variant="body2">
                      Active Leases: {monitoring.dhcpv6_stats.active_leases}
                    </Typography>
                    <LinearProgress 
                      variant="determinate" 
                      value={monitoring.dhcpv6_stats.pool_utilization} 
                      sx={{ my: 1 }}
                    />
                    <Typography variant="body2">
                      Pool Utilization: {monitoring.dhcpv6_stats.pool_utilization}%
                    </Typography>
                    <Typography variant="body2">
                      Requests/Hour: {monitoring.dhcpv6_stats.requests_per_hour}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Traffic Statistics" />
                  <CardContent>
                    <Typography variant="body2">
                      Bytes In: {monitoring.traffic_stats.bytes_in.toLocaleString()}
                    </Typography>
                    <Typography variant="body2">
                      Bytes Out: {monitoring.traffic_stats.bytes_out.toLocaleString()}
                    </Typography>
                    <Typography variant="body2">
                      Packets In: {monitoring.traffic_stats.packets_in.toLocaleString()}
                    </Typography>
                    <Typography variant="body2">
                      Packets Out: {monitoring.traffic_stats.packets_out.toLocaleString()}
                    </Typography>
                    <Typography variant="body2" color="error">
                      Errors: {monitoring.traffic_stats.errors}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </Box>
      )}

      {/* Subnet Dialog */}
      <Dialog open={subnetDialogOpen} onClose={() => {setSubnetDialogOpen(false); resetSubnetForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedSubnet ? 'Edit IPv6 Subnet' : 'Add IPv6 Subnet'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={8}>
              <TextField
                fullWidth
                label="IPv6 Subnet"
                value={subnetForm.subnet}
                onChange={(e) => setSubnetForm({ ...subnetForm, subnet: e.target.value })}
                placeholder="2001:db8::/64"
                helperText="Enter IPv6 subnet in CIDR notation"
                required
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                type="number"
                label="Prefix Length"
                value={subnetForm.prefix_length}
                onChange={(e) => setSubnetForm({ ...subnetForm, prefix_length: parseInt(e.target.value) || 64 })}
                inputProps={{ min: 1, max: 128 }}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Allocation Type</InputLabel>
                <Select
                  value={subnetForm.allocation_type}
                  onChange={(e) => setSubnetForm({ ...subnetForm, allocation_type: e.target.value as any })}
                  label="Allocation Type"
                >
                  <MenuItem value="customer">Customer</MenuItem>
                  <MenuItem value="infrastructure">Infrastructure</MenuItem>
                  <MenuItem value="pool">Pool</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={subnetForm.status}
                  onChange={(e) => setSubnetForm({ ...subnetForm, status: e.target.value as any })}
                  label="Status"
                >
                  <MenuItem value="active">Active</MenuItem>
                  <MenuItem value="reserved">Reserved</MenuItem>
                  <MenuItem value="deprecated">Deprecated</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="VLAN ID"
                value={subnetForm.vlan_id}
                onChange={(e) => setSubnetForm({ ...subnetForm, vlan_id: e.target.value })}
                inputProps={{ min: 1, max: 4094 }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Site ID"
                value={subnetForm.site_id}
                onChange={(e) => setSubnetForm({ ...subnetForm, site_id: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={subnetForm.description}
                onChange={(e) => setSubnetForm({ ...subnetForm, description: e.target.value })}
                multiline
                rows={2}
              />
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

      {/* Address Dialog */}
      <Dialog open={addressDialogOpen} onClose={() => {setAddressDialogOpen(false); resetAddressForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedAddress ? 'Edit IPv6 Address' : 'Add IPv6 Address'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="IPv6 Address"
                value={addressForm.address}
                onChange={(e) => setAddressForm({ ...addressForm, address: e.target.value })}
                placeholder="2001:db8::1"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Subnet</InputLabel>
                <Select
                  value={addressForm.subnet_id}
                  onChange={(e) => setAddressForm({ ...addressForm, subnet_id: e.target.value })}
                  label="Subnet"
                  required
                >
                  {subnets.map((subnet) => (
                    <MenuItem key={subnet.id} value={subnet.id}>
                      {subnet.subnet}/{subnet.prefix_length}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Address Type</InputLabel>
                <Select
                  value={addressForm.address_type}
                  onChange={(e) => setAddressForm({ ...addressForm, address_type: e.target.value as any })}
                  label="Address Type"
                >
                  <MenuItem value="static">Static</MenuItem>
                  <MenuItem value="dhcpv6">DHCPv6</MenuItem>
                  <MenuItem value="slaac">SLAAC</MenuItem>
                  <MenuItem value="link-local">Link-Local</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Customer ID"
                value={addressForm.customer_id}
                onChange={(e) => setAddressForm({ ...addressForm, customer_id: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Device ID"
                value={addressForm.device_id}
                onChange={(e) => setAddressForm({ ...addressForm, device_id: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Interface Name"
                value={addressForm.interface_name}
                onChange={(e) => setAddressForm({ ...addressForm, interface_name: e.target.value })}
                placeholder="eth0, ge-0/0/0, etc."
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={addressForm.description}
                onChange={(e) => setAddressForm({ ...addressForm, description: e.target.value })}
                multiline
                rows={2}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setAddressDialogOpen(false); resetAddressForm();}}>Cancel</Button>
          <Button onClick={handleCreateAddress} variant="contained">
            {selectedAddress ? 'Update' : 'Create'} Address
          </Button>
        </DialogActions>
      </Dialog>

      {/* Route Dialog */}
      <Dialog open={routeDialogOpen} onClose={() => {setRouteDialogOpen(false); resetRouteForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedRoute ? 'Edit IPv6 Route' : 'Add IPv6 Route'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={8}>
              <TextField
                fullWidth
                label="Destination"
                value={routeForm.destination}
                onChange={(e) => setRouteForm({ ...routeForm, destination: e.target.value })}
                placeholder="2001:db8:1::"
                required
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                type="number"
                label="Prefix Length"
                value={routeForm.prefix_length}
                onChange={(e) => setRouteForm({ ...routeForm, prefix_length: parseInt(e.target.value) || 64 })}
                inputProps={{ min: 1, max: 128 }}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Next Hop"
                value={routeForm.next_hop}
                onChange={(e) => setRouteForm({ ...routeForm, next_hop: e.target.value })}
                placeholder="2001:db8::1"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Interface"
                value={routeForm.interface}
                onChange={(e) => setRouteForm({ ...routeForm, interface: e.target.value })}
                placeholder="eth0, ge-0/0/0, etc."
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                type="number"
                label="Metric"
                value={routeForm.metric}
                onChange={(e) => setRouteForm({ ...routeForm, metric: parseInt(e.target.value) || 100 })}
                inputProps={{ min: 1, max: 65535 }}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Route Type</InputLabel>
                <Select
                  value={routeForm.route_type}
                  onChange={(e) => setRouteForm({ ...routeForm, route_type: e.target.value as any })}
                  label="Route Type"
                >
                  <MenuItem value="static">Static</MenuItem>
                  <MenuItem value="dynamic">Dynamic</MenuItem>
                  <MenuItem value="default">Default</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={routeForm.status}
                  onChange={(e) => setRouteForm({ ...routeForm, status: e.target.value as any })}
                  label="Status"
                >
                  <MenuItem value="active">Active</MenuItem>
                  <MenuItem value="inactive">Inactive</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={routeForm.description}
                onChange={(e) => setRouteForm({ ...routeForm, description: e.target.value })}
                multiline
                rows={2}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setRouteDialogOpen(false); resetRouteForm();}}>Cancel</Button>
          <Button onClick={handleCreateRoute} variant="contained">
            {selectedRoute ? 'Update' : 'Create'} Route
          </Button>
        </DialogActions>
      </Dialog>

      {/* Firewall Rule Dialog */}
      <Dialog open={firewallDialogOpen} onClose={() => {setFirewallDialogOpen(false); resetFirewallForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{selectedFirewallRule ? 'Edit IPv6 Firewall Rule' : 'Add IPv6 Firewall Rule'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Rule Name"
                value={firewallForm.name}
                onChange={(e) => setFirewallForm({ ...firewallForm, name: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Source"
                value={firewallForm.source}
                onChange={(e) => setFirewallForm({ ...firewallForm, source: e.target.value })}
                placeholder="2001:db8::/64 or any"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Destination"
                value={firewallForm.destination}
                onChange={(e) => setFirewallForm({ ...firewallForm, destination: e.target.value })}
                placeholder="2001:db8:1::/64 or any"
                required
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Protocol</InputLabel>
                <Select
                  value={firewallForm.protocol}
                  onChange={(e) => setFirewallForm({ ...firewallForm, protocol: e.target.value as any })}
                  label="Protocol"
                >
                  <MenuItem value="tcp">TCP</MenuItem>
                  <MenuItem value="udp">UDP</MenuItem>
                  <MenuItem value="icmpv6">ICMPv6</MenuItem>
                  <MenuItem value="any">Any</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Source Port"
                value={firewallForm.source_port}
                onChange={(e) => setFirewallForm({ ...firewallForm, source_port: e.target.value })}
                placeholder="80, 443, 1024-65535"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Destination Port"
                value={firewallForm.destination_port}
                onChange={(e) => setFirewallForm({ ...firewallForm, destination_port: e.target.value })}
                placeholder="80, 443, 1024-65535"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Action</InputLabel>
                <Select
                  value={firewallForm.action}
                  onChange={(e) => setFirewallForm({ ...firewallForm, action: e.target.value as any })}
                  label="Action"
                >
                  <MenuItem value="allow">Allow</MenuItem>
                  <MenuItem value="deny">Deny</MenuItem>
                  <MenuItem value="drop">Drop</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                type="number"
                label="Priority"
                value={firewallForm.priority}
                onChange={(e) => setFirewallForm({ ...firewallForm, priority: parseInt(e.target.value) || 100 })}
                inputProps={{ min: 1, max: 65535 }}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControlLabel
                control={
                  <Switch
                    checked={firewallForm.enabled}
                    onChange={(e) => setFirewallForm({ ...firewallForm, enabled: e.target.checked })}
                  />
                }
                label="Enabled"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={firewallForm.description}
                onChange={(e) => setFirewallForm({ ...firewallForm, description: e.target.value })}
                multiline
                rows={2}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setFirewallDialogOpen(false); resetFirewallForm();}}>Cancel</Button>
          <Button onClick={handleCreateFirewallRule} variant="contained">
            {selectedFirewallRule ? 'Update' : 'Create'} Rule
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleCancelDelete} maxWidth="sm" fullWidth>
        <DialogTitle>Delete IPv6 {deleteTarget?.type}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. This may affect network connectivity.
          </Alert>
          <Typography>
            Are you sure you want to delete <strong>{deleteTarget?.name}</strong>?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelDelete}>Cancel</Button>
          <Button 
            onClick={handleConfirmDelete} 
            variant="contained" 
            color="error"
            disabled={deleteLoading}
          >
            {deleteLoading ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default IPv6Management;