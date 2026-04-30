import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
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
  Alert,
  CircularProgress,
  Tabs,
  Tab,
  AccordionSummary,
  AccordionDetails,
  Accordion,
  LinearProgress,
  Tooltip
} from '@mui/material';
import {
  Search,
  Refresh,
  Settings,
  Timeline,
  NetworkCheck,
  Router as RouterIcon,
  DeviceHub,
  Cable,
  Info,
  Warning,
  CheckCircle,
  Error,
  ExpandMore,
  Visibility,
  PlayArrow,
  Stop,
  Download,
  Add
} from '@mui/icons-material';
import api from '../services/api';

interface LLDPNeighbor {
  id: number;
  local_device_id: string;
  local_port: string;
  remote_device_id: string;
  remote_port: string;
  remote_device_name: string;
  remote_system_description: string;
  remote_management_ip?: string;
  ttl: number;
  capabilities: string[];
  discovered_at: string;
  last_seen: string;
}

interface SNMPDevice {
  id: number;
  ip_address: string;
  hostname?: string;
  system_description: string;
  system_uptime: number;
  snmp_version: string;
  community_string?: string;
  contact?: string;
  location?: string;
  interfaces: SNMPInterface[];
  status: 'online' | 'offline' | 'unreachable';
  last_polled: string;
  response_time_ms: number;
}

interface SNMPInterface {
  index: number;
  name: string;
  description: string;
  type: string;
  mtu: number;
  speed: number;
  admin_status: 'up' | 'down' | 'testing';
  oper_status: 'up' | 'down' | 'unknown' | 'dormant' | 'notPresent' | 'lowerLayerDown';
  mac_address?: string;
  ip_addresses: string[];
  in_octets: number;
  out_octets: number;
  in_errors: number;
  out_errors: number;
  in_discards: number;
  out_discards: number;
}

interface DiscoveryJob {
  id: number;
  name: string;
  target_range: string;
  discovery_type: 'lldp' | 'snmp' | 'both';
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  devices_found: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

const NetworkDiscovery: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // LLDP State
  const [lldpNeighbors, setLldpNeighbors] = useState<LLDPNeighbor[]>([]);
  const [lldpLoading, setLldpLoading] = useState(false);
  
  // SNMP State
  const [snmpDevices, setSnmpDevices] = useState<SNMPDevice[]>([]);
  const [snmpLoading, setSnmpLoading] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<SNMPDevice | null>(null);
  const [deviceDetailsOpen, setDeviceDetailsOpen] = useState(false);
  
  // Discovery State
  const [discoveryJobs, setDiscoveryJobs] = useState<DiscoveryJob[]>([]);
  const [newJobDialogOpen, setNewJobDialogOpen] = useState(false);
  const [newJobForm, setNewJobForm] = useState({
    name: '',
    target_range: '',
    discovery_type: 'both' as 'lldp' | 'snmp' | 'both',
    snmp_community: 'public',
    snmp_version: '2c',
    timeout: 5,
    retries: 3
  });

  useEffect(() => {
    loadInitialData();
    
    // Set up auto-refresh every 30 seconds
    const interval = setInterval(loadInitialData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadLLDPNeighbors(),
        loadSNMPDevices(),
        loadDiscoveryJobs()
      ]);
    } catch (err) {
      setError('Failed to load network discovery data');
      console.error('Error loading discovery data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadLLDPNeighbors = async () => {
    setLldpLoading(true);
    try {
      const response = await api.get('/api/v1/network/lldp/neighbors');
      setLldpNeighbors(response.data || []);
    } catch (err) {
      console.error('Failed to load LLDP neighbors:', err);
      setLldpNeighbors([]);
    } finally {
      setLldpLoading(false);
    }
  };

  const loadSNMPDevices = async () => {
    setSnmpLoading(true);
    try {
      const response = await api.get('/api/v1/network/snmp/devices');
      setSnmpDevices(response.data || []);
    } catch (err) {
      console.error('Failed to load SNMP devices:', err);
      setSnmpDevices([]);
    } finally {
      setSnmpLoading(false);
    }
  };

  const loadDiscoveryJobs = async () => {
    try {
      const response = await api.get('/api/v1/network/discovery/jobs');
      setDiscoveryJobs(response.data || []);
    } catch (err) {
      console.error('Failed to load discovery jobs:', err);
      setDiscoveryJobs([]);
    }
  };

  const startLLDPDiscovery = async () => {
    try {
      setLldpLoading(true);
      await api.post('/api/v1/network/lldp/discover');
      await loadLLDPNeighbors();
    } catch (err) {
      setError('Failed to start LLDP discovery');
      console.error('Error starting LLDP discovery:', err);
    } finally {
      setLldpLoading(false);
    }
  };

  const pollSNMPDevice = async (deviceId: number) => {
    try {
      await api.post(`/api/v1/network/snmp/devices/${deviceId}/poll`);
      await loadSNMPDevices();
    } catch (err) {
      setError('Failed to poll SNMP device');
      console.error('Error polling SNMP device:', err);
    }
  };

  const startDiscoveryJob = async () => {
    try {
      await api.post('/api/v1/network/discovery/jobs', newJobForm);
      setNewJobDialogOpen(false);
      resetNewJobForm();
      await loadDiscoveryJobs();
    } catch (err) {
      setError('Failed to start discovery job');
      console.error('Error starting discovery job:', err);
    }
  };

  const resetNewJobForm = () => {
    setNewJobForm({
      name: '',
      target_range: '',
      discovery_type: 'both',
      snmp_community: 'public',
      snmp_version: '2c',
      timeout: 5,
      retries: 3
    });
  };

  const handleViewDeviceDetails = (device: SNMPDevice) => {
    setSelectedDevice(device);
    setDeviceDetailsOpen(true);
  };

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'online':
      case 'up':
        return <CheckCircle color="success" />;
      case 'offline':
      case 'down':
        return <Error color="error" />;
      case 'unreachable':
        return <Warning color="warning" />;
      default:
        return <Info color="info" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online':
      case 'up':
      case 'completed':
        return 'success';
      case 'offline':
      case 'down':
      case 'failed':
        return 'error';
      case 'unreachable':
      case 'warning':
        return 'warning';
      case 'running':
        return 'info';
      default:
        return 'default';
    }
  };

  const renderLLDPTab = () => (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6">LLDP Network Discovery</Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={loadLLDPNeighbors}
            disabled={lldpLoading}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={lldpLoading ? <CircularProgress size={16} /> : <Search />}
            onClick={startLLDPDiscovery}
            disabled={lldpLoading}
          >
            {lldpLoading ? 'Discovering...' : 'Start Discovery'}
          </Button>
        </Box>
      </Box>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            LLDP Neighbors ({lldpNeighbors.length})
          </Typography>
          {lldpLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Local Device</TableCell>
                    <TableCell>Local Port</TableCell>
                    <TableCell>Remote Device</TableCell>
                    <TableCell>Remote Port</TableCell>
                    <TableCell>Management IP</TableCell>
                    <TableCell>Capabilities</TableCell>
                    <TableCell>TTL</TableCell>
                    <TableCell>Last Seen</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {lldpNeighbors.length > 0 ? (
                    lldpNeighbors.map((neighbor) => (
                      <TableRow key={neighbor.id}>
                        <TableCell>{neighbor.local_device_id}</TableCell>
                        <TableCell>{neighbor.local_port}</TableCell>
                        <TableCell>
                          <Box>
                            <Typography variant="body2" fontWeight="medium">
                              {neighbor.remote_device_name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {neighbor.remote_device_id}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>{neighbor.remote_port}</TableCell>
                        <TableCell>{neighbor.remote_management_ip || 'N/A'}</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {neighbor.capabilities.map((cap, index) => (
                              <Chip key={index} label={cap} size="small" />
                            ))}
                          </Box>
                        </TableCell>
                        <TableCell>{neighbor.ttl}s</TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {new Date(neighbor.last_seen).toLocaleString()}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          No LLDP neighbors discovered. Click "Start Discovery" to scan.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>
    </Box>
  );

  const renderSNMPTab = () => (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6">SNMP Device Monitoring</Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={loadSNMPDevices}
            disabled={snmpLoading}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setNewJobDialogOpen(true)}
          >
            Add Device
          </Button>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {snmpDevices.map((device) => (
          <Grid item xs={12} md={6} lg={4} key={device.id}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <DeviceHub sx={{ mr: 1, color: 'primary.main' }} />
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="h6">
                      {device.hostname || device.ip_address}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {device.ip_address}
                    </Typography>
                  </Box>
                  <Chip
                    icon={getStatusIcon(device.status)}
                    label={device.status}
                    color={getStatusColor(device.status)}
                    size="small"
                  />
                </Box>

                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Uptime:</strong> {formatUptime(device.system_uptime)}
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Response:</strong> {device.response_time_ms}ms
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Interfaces:</strong> {device.interfaces.length}
                </Typography>
                <Typography variant="body2" sx={{ mb: 2 }}>
                  <strong>Last Polled:</strong> {new Date(device.last_polled).toLocaleString()}
                </Typography>

                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Button
                    size="small"
                    startIcon={<Visibility />}
                    onClick={() => handleViewDeviceDetails(device)}
                  >
                    Details
                  </Button>
                  <Button
                    size="small"
                    startIcon={<Refresh />}
                    onClick={() => pollSNMPDevice(device.id)}
                  >
                    Poll
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
        
        {snmpDevices.length === 0 && !snmpLoading && (
          <Grid item xs={12}>
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 4 }}>
                <Typography color="text.secondary">
                  No SNMP devices configured. Add devices to start monitoring.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Box>
  );

  const renderDiscoveryTab = () => (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6">Network Discovery Jobs</Typography>
        <Button
          variant="contained"
          startIcon={<PlayArrow />}
          onClick={() => setNewJobDialogOpen(true)}
        >
          New Discovery Job
        </Button>
      </Box>

      <Card>
        <CardContent>
          <TableContainer component={Paper} variant="outlined">
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Job Name</TableCell>
                  <TableCell>Target Range</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Progress</TableCell>
                  <TableCell>Devices Found</TableCell>
                  <TableCell>Started</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {discoveryJobs.length > 0 ? (
                  discoveryJobs.map((job) => (
                    <TableRow key={job.id}>
                      <TableCell>{job.name}</TableCell>
                      <TableCell>{job.target_range}</TableCell>
                      <TableCell>
                        <Chip label={job.discovery_type.toUpperCase()} size="small" />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={job.status}
                          color={getStatusColor(job.status)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        {job.status === 'running' ? (
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <LinearProgress
                              variant="determinate"
                              value={job.progress}
                              sx={{ flex: 1 }}
                            />
                            <Typography variant="body2">{job.progress}%</Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2">
                            {job.status === 'completed' ? '100%' : '-'}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>{job.devices_found}</TableCell>
                      <TableCell>
                        {job.started_at ? new Date(job.started_at).toLocaleString() : '-'}
                      </TableCell>
                      <TableCell>
                        <IconButton size="small">
                          <Visibility />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                      <Typography color="text.secondary">
                        No discovery jobs found. Create a new job to start network discovery.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Box>
  );

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            Network Discovery & Monitoring
          </Typography>
          <Typography variant="body1" color="text.secondary">
            LLDP topology discovery and SNMP device monitoring
          </Typography>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
            <Tab icon={<NetworkCheck />} label="LLDP Discovery" iconPosition="start" />
            <Tab icon={<DeviceHub />} label="SNMP Monitoring" iconPosition="start" />
            <Tab icon={<Timeline />} label="Discovery Jobs" iconPosition="start" />
          </Tabs>
        </Box>

        <CardContent sx={{ p: 3 }}>
          {tabValue === 0 && renderLLDPTab()}
          {tabValue === 1 && renderSNMPTab()}
          {tabValue === 2 && renderDiscoveryTab()}
        </CardContent>
      </Card>

      {/* Device Details Dialog */}
      <Dialog open={deviceDetailsOpen} onClose={() => setDeviceDetailsOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>
          SNMP Device Details - {selectedDevice?.hostname || selectedDevice?.ip_address}
        </DialogTitle>
        <DialogContent>
          {selectedDevice && (
            <Box sx={{ mt: 2 }}>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Device Information</Typography>
                  <Typography variant="body2"><strong>IP Address:</strong> {selectedDevice.ip_address}</Typography>
                  <Typography variant="body2"><strong>Hostname:</strong> {selectedDevice.hostname || 'N/A'}</Typography>
                  <Typography variant="body2"><strong>System Description:</strong> {selectedDevice.system_description}</Typography>
                  <Typography variant="body2"><strong>Contact:</strong> {selectedDevice.contact || 'N/A'}</Typography>
                  <Typography variant="body2"><strong>Location:</strong> {selectedDevice.location || 'N/A'}</Typography>
                  <Typography variant="body2"><strong>Uptime:</strong> {formatUptime(selectedDevice.system_uptime)}</Typography>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>SNMP Information</Typography>
                  <Typography variant="body2"><strong>Version:</strong> {selectedDevice.snmp_version}</Typography>
                  <Typography variant="body2"><strong>Status:</strong> {selectedDevice.status}</Typography>
                  <Typography variant="body2"><strong>Response Time:</strong> {selectedDevice.response_time_ms}ms</Typography>
                  <Typography variant="body2"><strong>Last Polled:</strong> {new Date(selectedDevice.last_polled).toLocaleString()}</Typography>
                </Grid>
              </Grid>

              <Typography variant="h6" sx={{ mt: 3, mb: 2 }}>Network Interfaces</Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Index</TableCell>
                      <TableCell>Name</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Speed</TableCell>
                      <TableCell>IP Addresses</TableCell>
                      <TableCell>Traffic</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {selectedDevice.interfaces.map((iface) => (
                      <TableRow key={iface.index}>
                        <TableCell>{iface.index}</TableCell>
                        <TableCell>
                          <Box>
                            <Typography variant="body2">{iface.name}</Typography>
                            <Typography variant="caption" color="text.secondary">
                              {iface.description}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>{iface.type}</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {getStatusIcon(iface.oper_status)}
                            <Typography variant="body2">{iface.oper_status}</Typography>
                          </Box>
                        </TableCell>
                        <TableCell>{iface.speed ? formatBytes(iface.speed) + '/s' : 'N/A'}</TableCell>
                        <TableCell>
                          {iface.ip_addresses.length > 0 ? (
                            <Box>
                              {iface.ip_addresses.map((ip, index) => (
                                <Typography key={index} variant="body2">{ip}</Typography>
                              ))}
                            </Box>
                          ) : (
                            'N/A'
                          )}
                        </TableCell>
                        <TableCell>
                          <Box>
                            <Typography variant="caption">
                              In: {formatBytes(iface.in_octets)}
                            </Typography>
                            <br />
                            <Typography variant="caption">
                              Out: {formatBytes(iface.out_octets)}
                            </Typography>
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeviceDetailsOpen(false)}>Close</Button>
          <Button variant="contained" startIcon={<Download />}>
            Export Data
          </Button>
        </DialogActions>
      </Dialog>

      {/* New Discovery Job Dialog */}
      <Dialog open={newJobDialogOpen} onClose={() => setNewJobDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Discovery Job</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Job Name"
                value={newJobForm.name}
                onChange={(e) => setNewJobForm({ ...newJobForm, name: e.target.value })}
                placeholder="e.g., Office Network Discovery"
                required
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Target Range"
                value={newJobForm.target_range}
                onChange={(e) => setNewJobForm({ ...newJobForm, target_range: e.target.value })}
                placeholder="e.g., 192.168.1.0/24 or 192.168.1.1-192.168.1.100"
                required
                helperText="Specify IP range in CIDR notation or range format"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Discovery Type</InputLabel>
                <Select
                  value={newJobForm.discovery_type}
                  onChange={(e) => setNewJobForm({ ...newJobForm, discovery_type: e.target.value as any })}
                  label="Discovery Type"
                >
                  <MenuItem value="lldp">LLDP Only</MenuItem>
                  <MenuItem value="snmp">SNMP Only</MenuItem>
                  <MenuItem value="both">Both LLDP & SNMP</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            {(newJobForm.discovery_type === 'snmp' || newJobForm.discovery_type === 'both') && (
              <>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="SNMP Community"
                    value={newJobForm.snmp_community}
                    onChange={(e) => setNewJobForm({ ...newJobForm, snmp_community: e.target.value })}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>SNMP Version</InputLabel>
                    <Select
                      value={newJobForm.snmp_version}
                      onChange={(e) => setNewJobForm({ ...newJobForm, snmp_version: e.target.value })}
                      label="SNMP Version"
                    >
                      <MenuItem value="1">v1</MenuItem>
                      <MenuItem value="2c">v2c</MenuItem>
                      <MenuItem value="3">v3</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </>
            )}
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Timeout (seconds)"
                value={newJobForm.timeout}
                onChange={(e) => setNewJobForm({ ...newJobForm, timeout: parseInt(e.target.value) || 5 })}
                inputProps={{ min: 1, max: 30 }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                type="number"
                label="Retries"
                value={newJobForm.retries}
                onChange={(e) => setNewJobForm({ ...newJobForm, retries: parseInt(e.target.value) || 3 })}
                inputProps={{ min: 0, max: 10 }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewJobDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={startDiscoveryJob}
            variant="contained"
            disabled={!newJobForm.name || !newJobForm.target_range}
          >
            Start Discovery
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default NetworkDiscovery;