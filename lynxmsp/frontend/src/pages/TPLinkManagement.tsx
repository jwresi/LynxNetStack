import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  CardActions,
  Button,
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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Tabs,
  Tab,
  Alert,
  Tooltip,
  Switch,
  FormControlLabel,
  LinearProgress,
  Badge
} from '@mui/material';
import {
  Router as RouterIcon,
  Cable,
  PowerSettingsNew,
  Settings,
  Add,
  Refresh,
  Delete,
  Warning,
  CheckCircle,
  Error as ErrorIcon,
  DeviceHub,
  Timeline,
  MonitorHeart,
  Visibility,
  Memory
} from '@mui/icons-material';
import api from '../services/api';
import ONTProvisionDialog from '../components/ONTProvisionDialog';

interface TPLinkDevice {
  id: number;
  device_id: string;
  sn: string;
  mac: string;
  name: string;
  model: string;
  device_type: string;
  firmware_version: string;
  ip_address: string;
  management_domain: string;
  status: string;
  site_id?: number;
  customer_id?: number;
  parent_device_id?: number;
  temperature?: number;
  power_consumption?: number;
  uptime?: number;
  alarm_count: number;
  last_seen?: string;
  created_at: string;
  updated_at: string;
}

interface TPLinkInterface {
  id: number;
  device_id: number;
  interface_name: string;
  alias?: string;
  interface_type: string;
  status: string;
  admin_status: string;
  speed?: string;
  duplex?: string;
  mtu: number;
  mac_address?: string;
  rx_bytes: number;
  tx_bytes: number;
  rx_packets: number;
  tx_packets: number;
  vlan_id?: number;
  description?: string;
  pon_port_number?: number;
  optical_power_tx?: number;
  optical_power_rx?: number;
  connected_onts?: number;
  ssid?: string;
  last_updated?: string;
}

interface DeviceStatus {
  device_id: string;
  status: string;
  uptime?: number;
  temperature?: number;
  power_consumption?: number;
  alarm_count: number;
  interface_count: number;
  last_updated: string;
}

function TPLinkManagement() {
  const [devices, setDevices] = useState<TPLinkDevice[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<TPLinkDevice | null>(null);
  const [interfaces, setInterfaces] = useState<TPLinkInterface[]>([]);
  const [deviceStatus, setDeviceStatus] = useState<DeviceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Dialog states
  const [addDeviceOpen, setAddDeviceOpen] = useState(false);
  const [deviceDetailsOpen, setDeviceDetailsOpen] = useState(false);
  const [portControlOpen, setPortControlOpen] = useState(false);
  const [ontProvisionOpen, setOntProvisionOpen] = useState(false);
  const [configureDeviceOpen, setConfigureDeviceOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [selectedInterface, setSelectedInterface] = useState<TPLinkInterface | null>(null);
  const [deviceToConfig, setDeviceToConfig] = useState<TPLinkDevice | null>(null);
  const [deviceToDelete, setDeviceToDelete] = useState<TPLinkDevice | null>(null);
  
  // Filters
  const [deviceTypeFilter, setDeviceTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [tabValue, setTabValue] = useState(0);

  // Form states
  const [newDevice, setNewDevice] = useState({
    device_id: '',
    sn: '',
    mac: '',
    name: '',
    model: '',
    device_type: '',
    management_domain: '',
    client_id: '',
    client_secret: '',
    network_id: '',
    site_id: undefined as number | undefined
  });

  const [portControl, setPortControl] = useState({
    action: 'enable',
    speed: '',
    duplex: '',
    vlan_id: undefined as number | undefined,
    description: ''
  });

  const [deviceConfig, setDeviceConfig] = useState({
    name: '',
    ip_address: '',
    management_domain: '',
    site_id: '',
    customer_id: '',
    snmp_community: 'public',
    snmp_version: '2c',
    firmware_auto_update: false,
    monitoring_enabled: true,
    location: '',
    description: ''
  });

  const loadDevices = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (deviceTypeFilter) params.append('device_type', deviceTypeFilter);
      if (statusFilter) params.append('status', statusFilter);
      
      const response = await api.get(`/tplink/devices?${params.toString()}`);
      setDevices(response.data || []);
      setError('');
    } catch (err: any) {
      console.error('Failed to fetch TP-Link devices:', err);
      setDevices([]);
      setError('Unable to connect to TP-Link TUAC API. Please check your connection settings.');
    } finally {
      setLoading(false);
    }
  }, [deviceTypeFilter, statusFilter]);

  useEffect(() => {
    loadDevices();
  }, [deviceTypeFilter, statusFilter, loadDevices]);

  useEffect(() => {
    if (selectedDevice) {
      loadDeviceInterfaces(selectedDevice.id);
      loadDeviceStatus(selectedDevice.id);
    }
  }, [selectedDevice]);

  const loadDeviceInterfaces = async (deviceId: number) => {
    try {
      const response = await api.get(`/tplink/devices/${deviceId}/interfaces?refresh=true`);
      setInterfaces(response.data || []);
    } catch (err) {
      setInterfaces([]);
      console.error('Error loading interfaces:', err);
    }
  };

  const loadDeviceStatus = async (deviceId: number) => {
    try {
      const response = await api.get(`/tplink/devices/${deviceId}/status?refresh=true`);
      setDeviceStatus(response.data);
    } catch (err) {
      setDeviceStatus(null);
      console.error('Error loading device status:', err);
    }
  };

  const handleAddDevice = async () => {
    try {
      await api.post('/tplink/devices', newDevice);
      setAddDeviceOpen(false);
      setNewDevice({
        device_id: '',
        sn: '',
        mac: '',
        name: '',
        model: '',
        device_type: '',
        management_domain: '',
        client_id: '',
        client_secret: '',
        network_id: '',
        site_id: undefined
      });
      loadDevices();
    } catch (err) {
      setError('Failed to add device');
      console.error('Error adding device:', err);
    }
  };

  const handlePortControl = async () => {
    if (!selectedDevice || !selectedInterface) return;

    try {
      await api.post(
        `/tplink/devices/${selectedDevice.id}/interfaces/${selectedInterface.interface_name}/control`,
        {
          action: portControl.action,
          interface_name: selectedInterface.interface_name,
          speed: portControl.speed || undefined,
          duplex: portControl.duplex || undefined,
          vlan_id: portControl.vlan_id || undefined,
          description: portControl.description || undefined
        }
      );
      
      setPortControlOpen(false);
      loadDeviceInterfaces(selectedDevice.id);
    } catch (err) {
      setError('Failed to control port');
      console.error('Error controlling port:', err);
    }
  };

  const handleConfigureDevice = (device: TPLinkDevice) => {
    setDeviceToConfig(device);
    setDeviceConfig({
      name: device.name || '',
      ip_address: device.ip_address || '',
      management_domain: device.management_domain || '',
      site_id: device.site_id?.toString() || '',
      customer_id: device.customer_id?.toString() || '',
      snmp_community: 'public',
      snmp_version: '2c',
      firmware_auto_update: false,
      monitoring_enabled: true,
      location: '',
      description: ''
    });
    setConfigureDeviceOpen(true);
  };

  const handleSaveDeviceConfig = async () => {
    if (!deviceToConfig) return;

    try {
      await api.put(`/tplink/devices/${deviceToConfig.id}/config`, {
        name: deviceConfig.name,
        ip_address: deviceConfig.ip_address,
        management_domain: deviceConfig.management_domain,
        site_id: deviceConfig.site_id ? parseInt(deviceConfig.site_id) : null,
        customer_id: deviceConfig.customer_id ? parseInt(deviceConfig.customer_id) : null,
        snmp_settings: {
          community: deviceConfig.snmp_community,
          version: deviceConfig.snmp_version
        },
        firmware_auto_update: deviceConfig.firmware_auto_update,
        monitoring_enabled: deviceConfig.monitoring_enabled,
        location: deviceConfig.location,
        description: deviceConfig.description
      });
      
      setConfigureDeviceOpen(false);
      setDeviceToConfig(null);
      loadDevices();
    } catch (err) {
      setError('Failed to save device configuration');
      console.error('Error saving device config:', err);
    }
  };

  const handleCancelDeviceConfig = () => {
    setConfigureDeviceOpen(false);
    setDeviceToConfig(null);
    setDeviceConfig({
      name: '',
      ip_address: '',
      management_domain: '',
      site_id: '',
      customer_id: '',
      snmp_community: 'public',
      snmp_version: '2c',
      firmware_auto_update: false,
      monitoring_enabled: true,
      location: '',
      description: ''
    });
  };

  const handleDeleteDevice = (device: TPLinkDevice) => {
    setDeviceToDelete(device);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!deviceToDelete) return;
    
    setDeleteLoading(true);
    try {
      await api.delete(`/tplink/devices/${deviceToDelete.id}`);
      setDeleteDialogOpen(false);
      setDeviceToDelete(null);
      loadDevices();
    } catch (err) {
      setError('Failed to delete device');
      console.error('Error deleting device:', err);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCancelDelete = () => {
    setDeleteDialogOpen(false);
    setDeviceToDelete(null);
  };

  const getDeviceTypeIcon = (deviceType: string) => {
    if (deviceType.includes('olt')) return <RouterIcon />;
    if (deviceType.includes('ont')) return <DeviceHub />;
    return <Cable />;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': return 'success';
      case 'offline': return 'error';
      case 'maintenance': return 'warning';
      default: return 'default';
    }
  };

  const getInterfaceStatusIcon = (status: string) => {
    switch (status) {
      case 'up': return <CheckCircle color="success" />;
      case 'down': return <ErrorIcon color="error" />;
      case 'disabled': return <PowerSettingsNew color="disabled" />;
      default: return <Warning color="warning" />;
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatUptime = (seconds?: number) => {
    if (!seconds) return 'Unknown';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">TPLink Device Management</Typography>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setAddDeviceOpen(true)}
        >
          Add Device
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Device Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth>
              <InputLabel>Device Type</InputLabel>
              <Select
                value={deviceTypeFilter}
                onChange={(e) => setDeviceTypeFilter(e.target.value)}
                label="Device Type"
              >
                <MenuItem value="">All Types</MenuItem>
                <MenuItem value="olt_pizzabox_4">OLT PizzaBox 4-Port</MenuItem>
                <MenuItem value="olt_pizzabox_8">OLT PizzaBox 8-Port</MenuItem>
                <MenuItem value="ont_xz000_g7">ONT XZ000-G7</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth>
              <InputLabel>Status</InputLabel>
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                label="Status"
              >
                <MenuItem value="">All Status</MenuItem>
                <MenuItem value="online">Online</MenuItem>
                <MenuItem value="offline">Offline</MenuItem>
                <MenuItem value="maintenance">Maintenance</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={loadDevices}
              fullWidth
            >
              Refresh
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {loading ? (
        <LinearProgress />
      ) : (
        <Grid container spacing={3}>
          {/* Device List */}
          <Grid item xs={12} lg={selectedDevice ? 6 : 12}>
            <Paper>
              <Box p={2}>
                <Typography variant="h6" gutterBottom>
                  Devices ({devices.length})
                </Typography>
                <Grid container spacing={2}>
                  {devices.map((device) => (
                    <Grid item xs={12} sm={6} md={4} key={device.id}>
                      <Card
                        sx={{
                          cursor: 'pointer',
                          border: selectedDevice?.id === device.id ? '2px solid primary.main' : '1px solid',
                          borderColor: selectedDevice?.id === device.id ? 'primary.main' : 'divider'
                        }}
                        onClick={() => setSelectedDevice(device)}
                      >
                        <CardHeader
                          avatar={getDeviceTypeIcon(device.device_type)}
                          title={device.name}
                          subheader={device.model}
                          action={
                            <Badge badgeContent={device.alarm_count} color="error">
                              <Chip
                                label={device.status}
                                color={getStatusColor(device.status) as any}
                                size="small"
                              />
                            </Badge>
                          }
                        />
                        <CardContent>
                          <Typography variant="body2" color="text.secondary">
                            IP: {device.ip_address}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Type: {device.device_type.replace(/_/g, ' ').toUpperCase()}
                          </Typography>
                          {device.temperature && (
                            <Typography variant="body2" color="text.secondary">
                              Temp: {device.temperature}°C
                            </Typography>
                          )}
                        </CardContent>
                        <CardActions>
                          <Button
                            size="small"
                            startIcon={<Visibility />}
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeviceDetailsOpen(true);
                            }}
                          >
                            Details
                          </Button>
                          {device.device_type.includes('olt') && (
                            <Button
                              size="small"
                              startIcon={<Add />}
                              onClick={(e) => {
                                e.stopPropagation();
                                setOntProvisionOpen(true);
                              }}
                              color="primary"
                            >
                              Provision ONT
                            </Button>
                          )}
                          <Button
                            size="small"
                            startIcon={<Settings />}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleConfigureDevice(device);
                            }}
                          >
                            Configure
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            startIcon={<Delete />}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteDevice(device);
                            }}
                          >
                            Delete
                          </Button>
                        </CardActions>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </Box>
            </Paper>
          </Grid>

          {/* Device Details Panel */}
          {selectedDevice && (
            <Grid item xs={12} lg={6}>
              <Paper>
                <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
                  <Tab label="Overview" />
                  <Tab label="Interfaces" />
                  <Tab label="Performance" />
                  <Tab label="Alarms" />
                </Tabs>

                {/* Overview Tab */}
                {tabValue === 0 && (
                  <Box p={2}>
                    <Typography variant="h6" gutterBottom>
                      Device Overview: {selectedDevice.name}
                    </Typography>
                    
                    {deviceStatus && (
                      <Grid container spacing={2} sx={{ mb: 3 }}>
                        <Grid item xs={6} sm={3}>
                          <Card>
                            <CardContent sx={{ textAlign: 'center' }}>
                              <MonitorHeart color="primary" />
                              <Typography variant="h6">{deviceStatus.status}</Typography>
                              <Typography variant="caption">Status</Typography>
                            </CardContent>
                          </Card>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Card>
                            <CardContent sx={{ textAlign: 'center' }}>
                              <Timeline color="primary" />
                              <Typography variant="h6">{formatUptime(deviceStatus.uptime)}</Typography>
                              <Typography variant="caption">Uptime</Typography>
                            </CardContent>
                          </Card>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Card>
                            <CardContent sx={{ textAlign: 'center' }}>
                              <Memory color="primary" />
                              <Typography variant="h6">{deviceStatus.temperature || 'N/A'}</Typography>
                              <Typography variant="caption">Temperature</Typography>
                            </CardContent>
                          </Card>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Card>
                            <CardContent sx={{ textAlign: 'center' }}>
                              <Warning color={deviceStatus.alarm_count > 0 ? 'error' : 'disabled'} />
                              <Typography variant="h6">{deviceStatus.alarm_count}</Typography>
                              <Typography variant="caption">Alarms</Typography>
                            </CardContent>
                          </Card>
                        </Grid>
                      </Grid>
                    )}

                    <Grid container spacing={2}>
                      <Grid item xs={12} sm={6}>
                        <Typography variant="subtitle2">Device Information</Typography>
                        <Typography variant="body2">Serial: {selectedDevice.sn}</Typography>
                        <Typography variant="body2">MAC: {selectedDevice.mac}</Typography>
                        <Typography variant="body2">Firmware: {selectedDevice.firmware_version}</Typography>
                        <Typography variant="body2">Model: {selectedDevice.model}</Typography>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Typography variant="subtitle2">Network Configuration</Typography>
                        <Typography variant="body2">IP: {selectedDevice.ip_address}</Typography>
                        <Typography variant="body2">Domain: {selectedDevice.management_domain}</Typography>
                        <Typography variant="body2">Type: {selectedDevice.device_type}</Typography>
                      </Grid>
                    </Grid>
                  </Box>
                )}

                {/* Interfaces Tab */}
                {tabValue === 1 && (
                  <Box p={2}>
                    <Typography variant="h6" gutterBottom>
                      Network Interfaces
                    </Typography>
                    
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Interface</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Speed</TableCell>
                            <TableCell>RX/TX</TableCell>
                            <TableCell>Actions</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {interfaces.map((iface) => (
                            <TableRow key={iface.id}>
                              <TableCell>
                                <Box display="flex" alignItems="center">
                                  {getInterfaceStatusIcon(iface.status)}
                                  <Box ml={1}>
                                    <Typography variant="body2">{iface.interface_name}</Typography>
                                    {iface.alias && (
                                      <Typography variant="caption" color="text.secondary">
                                        {iface.alias}
                                      </Typography>
                                    )}
                                  </Box>
                                </Box>
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={iface.admin_status}
                                  color={iface.admin_status === 'enabled' ? 'success' : 'error'}
                                  size="small"
                                />
                              </TableCell>
                              <TableCell>{iface.speed || 'Auto'}</TableCell>
                              <TableCell>
                                <Typography variant="caption" display="block">
                                  RX: {formatBytes(iface.rx_bytes)}
                                </Typography>
                                <Typography variant="caption" display="block">
                                  TX: {formatBytes(iface.tx_bytes)}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Tooltip title="Port Control">
                                  <IconButton
                                    size="small"
                                    onClick={() => {
                                      setSelectedInterface(iface);
                                      setPortControlOpen(true);
                                    }}
                                  >
                                    <Settings />
                                  </IconButton>
                                </Tooltip>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Box>
                )}

                {/* Performance Tab */}
                {tabValue === 2 && (
                  <Box p={2}>
                    <Typography variant="h6" gutterBottom>
                      Performance Metrics
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Performance monitoring coming soon...
                    </Typography>
                  </Box>
                )}

                {/* Alarms Tab */}
                {tabValue === 3 && (
                  <Box p={2}>
                    <Typography variant="h6" gutterBottom>
                      Active Alarms
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Alarm management coming soon...
                    </Typography>
                  </Box>
                )}
              </Paper>
            </Grid>
          )}
        </Grid>
      )}

      {/* Add Device Dialog */}
      <Dialog open={addDeviceOpen} onClose={() => setAddDeviceOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Add TPLink Device</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Device ID"
                value={newDevice.device_id}
                onChange={(e) => setNewDevice({ ...newDevice, device_id: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Device Name"
                value={newDevice.name}
                onChange={(e) => setNewDevice({ ...newDevice, name: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Serial Number"
                value={newDevice.sn}
                onChange={(e) => setNewDevice({ ...newDevice, sn: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="MAC Address"
                value={newDevice.mac}
                onChange={(e) => setNewDevice({ ...newDevice, mac: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Model"
                value={newDevice.model}
                onChange={(e) => setNewDevice({ ...newDevice, model: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Device Type</InputLabel>
                <Select
                  value={newDevice.device_type}
                  onChange={(e) => setNewDevice({ ...newDevice, device_type: e.target.value })}
                  label="Device Type"
                >
                  <MenuItem value="olt_pizzabox_4">OLT PizzaBox 4-Port</MenuItem>
                  <MenuItem value="olt_pizzabox_8">OLT PizzaBox 8-Port</MenuItem>
                  <MenuItem value="ont_xz000_g7">ONT XZ000-G7</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Management Domain"
                value={newDevice.management_domain}
                onChange={(e) => setNewDevice({ ...newDevice, management_domain: e.target.value })}
                helperText="TAUC domain (e.g., your-domain.tplinkcloud.com)"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Client ID"
                value={newDevice.client_id}
                onChange={(e) => setNewDevice({ ...newDevice, client_id: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Client Secret"
                type="password"
                value={newDevice.client_secret}
                onChange={(e) => setNewDevice({ ...newDevice, client_secret: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Network ID"
                value={newDevice.network_id}
                onChange={(e) => setNewDevice({ ...newDevice, network_id: e.target.value })}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDeviceOpen(false)}>Cancel</Button>
          <Button onClick={handleAddDevice} variant="contained">Add Device</Button>
        </DialogActions>
      </Dialog>

      {/* Port Control Dialog */}
      <Dialog open={portControlOpen} onClose={() => setPortControlOpen(false)}>
        <DialogTitle>
          Port Control: {selectedInterface?.interface_name}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Action</InputLabel>
                <Select
                  value={portControl.action}
                  onChange={(e) => setPortControl({ ...portControl, action: e.target.value })}
                  label="Action"
                >
                  <MenuItem value="enable">Enable</MenuItem>
                  <MenuItem value="disable">Disable</MenuItem>
                  <MenuItem value="configure">Configure</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            {portControl.action === 'configure' && (
              <>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Speed</InputLabel>
                    <Select
                      value={portControl.speed}
                      onChange={(e) => setPortControl({ ...portControl, speed: e.target.value })}
                      label="Speed"
                    >
                      <MenuItem value="">Auto</MenuItem>
                      <MenuItem value="10Mbps">10 Mbps</MenuItem>
                      <MenuItem value="100Mbps">100 Mbps</MenuItem>
                      <MenuItem value="1Gbps">1 Gbps</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Duplex</InputLabel>
                    <Select
                      value={portControl.duplex}
                      onChange={(e) => setPortControl({ ...portControl, duplex: e.target.value })}
                      label="Duplex"
                    >
                      <MenuItem value="">Auto</MenuItem>
                      <MenuItem value="half">Half</MenuItem>
                      <MenuItem value="full">Full</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="VLAN ID"
                    type="number"
                    value={portControl.vlan_id || ''}
                    onChange={(e) => setPortControl({ 
                      ...portControl, 
                      vlan_id: e.target.value ? parseInt(e.target.value) : undefined 
                    })}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Description"
                    value={portControl.description}
                    onChange={(e) => setPortControl({ ...portControl, description: e.target.value })}
                  />
                </Grid>
              </>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPortControlOpen(false)}>Cancel</Button>
          <Button onClick={handlePortControl} variant="contained">Apply</Button>
        </DialogActions>
      </Dialog>

      {/* ONT Provision Dialog */}
      <ONTProvisionDialog
        open={ontProvisionOpen}
        onClose={() => setOntProvisionOpen(false)}
        oltDeviceId={selectedDevice?.id}
        onSuccess={() => {
          loadDevices();
          if (selectedDevice) {
            loadDeviceInterfaces(selectedDevice.id);
          }
        }}
      />

      {/* Device Configuration Dialog */}
      <Dialog open={configureDeviceOpen} onClose={handleCancelDeviceConfig} maxWidth="md" fullWidth>
        <DialogTitle>Configure Device: {deviceToConfig?.name}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Device Name"
                value={deviceConfig.name}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, name: e.target.value })}
                margin="normal"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="IP Address"
                value={deviceConfig.ip_address}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, ip_address: e.target.value })}
                margin="normal"
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Management Domain"
                value={deviceConfig.management_domain}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, management_domain: e.target.value })}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Site ID"
                type="number"
                value={deviceConfig.site_id}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, site_id: e.target.value })}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Customer ID"
                type="number"
                value={deviceConfig.customer_id}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, customer_id: e.target.value })}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Location"
                value={deviceConfig.location}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, location: e.target.value })}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={deviceConfig.description}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, description: e.target.value })}
                margin="normal"
                multiline
                rows={2}
              />
            </Grid>
            
            <Grid item xs={12}>
              <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>SNMP Settings</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="SNMP Community"
                value={deviceConfig.snmp_community}
                onChange={(e) => setDeviceConfig({ ...deviceConfig, snmp_community: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>SNMP Version</InputLabel>
                <Select
                  value={deviceConfig.snmp_version}
                  onChange={(e) => setDeviceConfig({ ...deviceConfig, snmp_version: e.target.value })}
                  label="SNMP Version"
                >
                  <MenuItem value="1">Version 1</MenuItem>
                  <MenuItem value="2c">Version 2c</MenuItem>
                  <MenuItem value="3">Version 3</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12}>
              <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>Device Options</Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={deviceConfig.firmware_auto_update}
                    onChange={(e) => setDeviceConfig({ ...deviceConfig, firmware_auto_update: e.target.checked })}
                  />
                }
                label="Automatic Firmware Updates"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={deviceConfig.monitoring_enabled}
                    onChange={(e) => setDeviceConfig({ ...deviceConfig, monitoring_enabled: e.target.checked })}
                  />
                }
                label="Monitoring Enabled"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelDeviceConfig}>Cancel</Button>
          <Button 
            onClick={handleSaveDeviceConfig} 
            variant="contained"
            disabled={!deviceConfig.name || !deviceConfig.ip_address}
          >
            Save Configuration
          </Button>
        </DialogActions>
      </Dialog>

      {/* Device Details Dialog */}
      <Dialog open={deviceDetailsOpen} onClose={() => setDeviceDetailsOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Device Details: {selectedDevice?.name}</DialogTitle>
        <DialogContent>
          {selectedDevice && (
            <Box sx={{ mt: 2 }}>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Basic Information</Typography>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Device ID</Typography>
                    <Typography variant="body1">{selectedDevice.device_id}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Serial Number</Typography>
                    <Typography variant="body1">{selectedDevice.sn}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">MAC Address</Typography>
                    <Typography variant="body1">{selectedDevice.mac}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Model</Typography>
                    <Typography variant="body1">{selectedDevice.model}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Firmware Version</Typography>
                    <Typography variant="body1">{selectedDevice.firmware_version}</Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Network Information</Typography>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">IP Address</Typography>
                    <Typography variant="body1">{selectedDevice.ip_address}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Management Domain</Typography>
                    <Typography variant="body1">{selectedDevice.management_domain}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Device Type</Typography>
                    <Typography variant="body1" sx={{ textTransform: 'capitalize' }}>
                      {selectedDevice.device_type.replace(/_/g, ' ')}
                    </Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Status</Typography>
                    <Chip
                      label={selectedDevice.status}
                      color={getStatusColor(selectedDevice.status)}
                      size="small"
                    />
                  </Box>
                </Grid>

                {(selectedDevice.temperature || selectedDevice.power_consumption || selectedDevice.uptime) && (
                  <Grid item xs={12}>
                    <Typography variant="h6" gutterBottom>Performance Metrics</Typography>
                    <Grid container spacing={2}>
                      {selectedDevice.temperature && (
                        <Grid item xs={4}>
                          <Box textAlign="center">
                            <Typography variant="h4" color="primary">{selectedDevice.temperature}°C</Typography>
                            <Typography variant="caption">Temperature</Typography>
                          </Box>
                        </Grid>
                      )}
                      {selectedDevice.power_consumption && (
                        <Grid item xs={4}>
                          <Box textAlign="center">
                            <Typography variant="h4" color="secondary">{selectedDevice.power_consumption}W</Typography>
                            <Typography variant="caption">Power Usage</Typography>
                          </Box>
                        </Grid>
                      )}
                      {selectedDevice.uptime && (
                        <Grid item xs={4}>
                          <Box textAlign="center">
                            <Typography variant="h4" color="success.main">{formatUptime(selectedDevice.uptime)}</Typography>
                            <Typography variant="caption">Uptime</Typography>
                          </Box>
                        </Grid>
                      )}
                    </Grid>
                  </Grid>
                )}

                {selectedDevice.alarm_count > 0 && (
                  <Grid item xs={12}>
                    <Alert severity="warning">
                      This device has {selectedDevice.alarm_count} active alarm{selectedDevice.alarm_count !== 1 ? 's' : ''}.
                    </Alert>
                  </Grid>
                )}
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeviceDetailsOpen(false)}>Close</Button>
          {selectedDevice && (
            <Button
              onClick={() => {
                setDeviceDetailsOpen(false);
                handleConfigureDevice(selectedDevice);
              }}
              variant="contained"
              startIcon={<Settings />}
            >
              Configure Device
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Delete Device Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleCancelDelete} maxWidth="sm" fullWidth>
        <DialogTitle>Delete TPLink Device</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. The device will be removed from management and monitoring.
          </Alert>
          <Typography>
            Are you sure you want to delete device <strong>{deviceToDelete?.name}</strong>?
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
            {deleteLoading ? 'Deleting...' : 'Delete Device'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default TPLinkManagement;