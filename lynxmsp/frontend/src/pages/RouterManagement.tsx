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
  Tabs,
  Tab,
  Alert,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Switch,
  FormControlLabel,
  Divider
} from '@mui/material';
import {
  Router as RouterIcon,
  Add,
  Edit,
  Delete,
  Refresh,
  Settings,
  ExpandMore,
  NetworkCheck,
  Cable,
  Memory,
  Speed,
  MonitorHeart,
  Code,
  Assignment,
  CheckCircle,
  Error,
  Warning
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api from '../services/api';

interface Router {
  id: number;
  name: string;
  model: string;
  ip_address: string;
  site_id: number;
  status: string;
  customer_vlan_start?: number;
  customer_subnet?: string;
  enable_dhcp_option82?: boolean;
  enable_customer_isolation?: boolean;
}

interface Site {
  id: number;
  name: string;
  location: string;
}

interface MonitoringData {
  timestamp: string;
  cpu_usage: number;
  memory_usage: number;
  uptime: string;
  temperature?: number;
}

interface RouterDetails {
  router: Router;
  monitoring_data: MonitoringData[];
  interfaces: any[];
  customer_vlans: any[];
  statistics: {
    uptime?: string;
    cpu_usage?: number;
    memory_usage?: number;
    temperature?: number;
  };
}

const RouterManagement: React.FC = () => {
  const [routers, setRouters] = useState<Router[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedRouter, setSelectedRouter] = useState<Router | null>(null);
  const [routerDetails, setRouterDetails] = useState<RouterDetails | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [onboardDialogOpen, setOnboardDialogOpen] = useState(false);
  const [monitoringDialogOpen, setMonitoringDialogOpen] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [onboardingResult, setOnboardingResult] = useState<any>(null);

  const [newRouter, setNewRouter] = useState({
    name: '',
    model: '',
    ip_address: '',
    site_id: '',
    customer_vlan_start: 100,
    customer_subnet: '',
    enable_dhcp_option82: true,
    enable_customer_isolation: true
  });

  useEffect(() => {
    fetchRouters();
    fetchSites();
  }, []);

  const fetchRouters = async () => {
    try {
      const response = await api.get('/routers');
      setRouters(response.data);
    } catch (error) {
      console.error('Failed to fetch routers:', error);
    }
  };

  const fetchSites = async () => {
    try {
      const response = await api.get('/sites');
      setSites(response.data);
    } catch (error) {
      console.error('Failed to fetch sites:', error);
    }
  };

  const fetchRouterDetails = async (routerId: number) => {
    setLoading(true);
    try {
      const response = await api.get(`/routers/${routerId}/monitoring`);
      setRouterDetails(response.data);
    } catch (error) {
      console.error('Failed to fetch router details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRouterClick = (router: Router) => {
    setSelectedRouter(router);
    fetchRouterDetails(router.id);
    setMonitoringDialogOpen(true);
  };

  const handleOnboardRouter = async () => {
    setLoading(true);
    try {
      const response = await api.post('/routers/onboard', newRouter);
      setOnboardingResult(response.data);
      setNewRouter({
        name: '',
        model: '',
        ip_address: '',
        site_id: '',
        customer_vlan_start: 100,
        customer_subnet: '',
        enable_dhcp_option82: true,
        enable_customer_isolation: true
      });
      fetchRouters();
    } catch (error) {
      console.error('Failed to onboard router:', error);
    } finally {
      setLoading(false);
    }
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
        return <RouterIcon />;
    }
  };

  const getSiteName = (siteId: number) => {
    const site = sites.find(s => s.id === siteId);
    return site ? site.name : 'Unknown Site';
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RouterIcon />
          Router Management
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchRouters}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setOnboardDialogOpen(true)}
          >
            Onboard Router
          </Button>
        </Box>
      </Box>

      {/* Router List */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Network Routers ({routers.length})
          </Typography>
          <TableContainer component={Paper} variant="outlined">
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Status</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Model</TableCell>
                  <TableCell>IP Address</TableCell>
                  <TableCell>Site</TableCell>
                  <TableCell>VLAN Range</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {routers.map((router) => (
                  <TableRow 
                    key={router.id}
                    sx={{ '&:hover': { backgroundColor: 'action.hover', cursor: 'pointer' } }}
                    onClick={() => handleRouterClick(router)}
                  >
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {getStatusIcon(router.status)}
                        <Chip 
                          label={router.status} 
                          color={getStatusColor(router.status)}
                          size="small"
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="subtitle2">{router.name}</Typography>
                    </TableCell>
                    <TableCell>{router.model}</TableCell>
                    <TableCell>{router.ip_address}</TableCell>
                    <TableCell>{getSiteName(router.site_id)}</TableCell>
                    <TableCell>
                      {router.customer_vlan_start ? `${router.customer_vlan_start}+` : 'Not set'}
                    </TableCell>
                    <TableCell>
                      <IconButton size="small" onClick={(e) => {
                        e.stopPropagation();
                        setSelectedRouter(router);
                        setDialogOpen(true);
                      }}>
                        <Edit />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Router Onboarding Dialog */}
      <Dialog open={onboardDialogOpen} onClose={() => setOnboardDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RouterIcon />
            Router Onboarding Wizard
          </Box>
        </DialogTitle>
        <DialogContent>
          {onboardingResult ? (
            <Box>
              <Alert severity="success" sx={{ mb: 3 }}>
                Router {onboardingResult.message}
              </Alert>
              
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Code />
                    Generated Configuration
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <TextField
                    multiline
                    rows={15}
                    fullWidth
                    value={onboardingResult.configuration}
                    variant="outlined"
                    sx={{ fontFamily: 'monospace' }}
                  />
                </AccordionDetails>
              </Accordion>

              <Accordion sx={{ mt: 2 }}>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Assignment />
                    Next Steps
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <ol>
                    {onboardingResult.next_steps?.map((step: string, index: number) => (
                      <li key={index}>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          {step}
                        </Typography>
                      </li>
                    ))}
                  </ol>
                </AccordionDetails>
              </Accordion>
            </Box>
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Router Name"
                  value={newRouter.name}
                  onChange={(e) => setNewRouter({...newRouter, name: e.target.value})}
                  margin="normal"
                />
                <TextField
                  fullWidth
                  label="Model"
                  value={newRouter.model}
                  onChange={(e) => setNewRouter({...newRouter, model: e.target.value})}
                  margin="normal"
                />
                <TextField
                  fullWidth
                  label="IP Address"
                  value={newRouter.ip_address}
                  onChange={(e) => setNewRouter({...newRouter, ip_address: e.target.value})}
                  margin="normal"
                />
                <FormControl fullWidth margin="normal">
                  <InputLabel>Site</InputLabel>
                  <Select
                    value={newRouter.site_id}
                    onChange={(e) => setNewRouter({...newRouter, site_id: e.target.value})}
                    label="Site"
                  >
                    {sites.map((site) => (
                      <MenuItem key={site.id} value={site.id}>
                        {site.name} - {site.location}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Customer VLAN Start"
                  type="number"
                  value={newRouter.customer_vlan_start}
                  onChange={(e) => setNewRouter({...newRouter, customer_vlan_start: parseInt(e.target.value)})}
                  margin="normal"
                />
                <TextField
                  fullWidth
                  label="Customer Subnet (e.g., 192.168.1.1/24)"
                  value={newRouter.customer_subnet}
                  onChange={(e) => setNewRouter({...newRouter, customer_subnet: e.target.value})}
                  margin="normal"
                />
                
                <Box sx={{ mt: 2 }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={newRouter.enable_dhcp_option82}
                        onChange={(e) => setNewRouter({...newRouter, enable_dhcp_option82: e.target.checked})}
                      />
                    }
                    label="Enable DHCP Option 82"
                  />
                </Box>
                
                <Box>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={newRouter.enable_customer_isolation}
                        onChange={(e) => setNewRouter({...newRouter, enable_customer_isolation: e.target.checked})}
                      />
                    }
                    label="Enable Customer Isolation"
                  />
                </Box>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setOnboardDialogOpen(false);
            setOnboardingResult(null);
          }}>
            Close
          </Button>
          {!onboardingResult && (
            <Button 
              onClick={handleOnboardRouter} 
              variant="contained"
              disabled={loading || !newRouter.name || !newRouter.ip_address || !newRouter.site_id}
            >
              {loading ? 'Onboarding...' : 'Onboard Router'}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Router Monitoring Dialog */}
      <Dialog 
        open={monitoringDialogOpen} 
        onClose={() => setMonitoringDialogOpen(false)} 
        maxWidth="lg" 
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <MonitorHeart />
            {selectedRouter?.name} - Monitoring Dashboard
          </Box>
        </DialogTitle>
        <DialogContent>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
              <LinearProgress sx={{ width: '100%' }} />
            </Box>
          ) : routerDetails ? (
            <Box>
              <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
                <Tab label="Overview" />
                <Tab label="Performance" />
                <Tab label="Interfaces" />
                <Tab label="Customer VLANs" />
              </Tabs>

              {tabValue === 0 && (
                <Box sx={{ mt: 2 }}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <RouterIcon />
                            Router Information
                          </Typography>
                          <Divider sx={{ mb: 2 }} />
                          <Typography><strong>Model:</strong> {routerDetails.router.model}</Typography>
                          <Typography><strong>IP Address:</strong> {routerDetails.router.ip_address}</Typography>
                          <Typography><strong>Status:</strong> 
                            <Chip 
                              label={routerDetails.router.status} 
                              color={getStatusColor(routerDetails.router.status)}
                              size="small"
                              sx={{ ml: 1 }}
                            />
                          </Typography>
                          {routerDetails.statistics.uptime && (
                            <Typography><strong>Uptime:</strong> {routerDetails.statistics.uptime}</Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                    
                    <Grid item xs={12} md={6}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Speed />
                            Performance Metrics
                          </Typography>
                          <Divider sx={{ mb: 2 }} />
                          {routerDetails.statistics.cpu_usage && (
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2">CPU Usage: {routerDetails.statistics.cpu_usage}%</Typography>
                              <LinearProgress 
                                variant="determinate" 
                                value={routerDetails.statistics.cpu_usage} 
                                sx={{ mt: 1 }}
                              />
                            </Box>
                          )}
                          {routerDetails.statistics.memory_usage && (
                            <Box sx={{ mb: 2 }}>
                              <Typography variant="body2">Memory Usage: {routerDetails.statistics.memory_usage}%</Typography>
                              <LinearProgress 
                                variant="determinate" 
                                value={routerDetails.statistics.memory_usage} 
                                sx={{ mt: 1 }}
                              />
                            </Box>
                          )}
                          {routerDetails.statistics.temperature && (
                            <Typography><strong>Temperature:</strong> {routerDetails.statistics.temperature}°C</Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                  </Grid>
                </Box>
              )}

              {tabValue === 1 && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="h6" gutterBottom>Performance Charts</Typography>
                  {routerDetails.monitoring_data && routerDetails.monitoring_data.length > 0 ? (
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={6}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Memory />
                              CPU Usage Over Time
                            </Typography>
                            <ResponsiveContainer width="100%" height={300}>
                              <LineChart data={routerDetails.monitoring_data}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="timestamp" />
                                <YAxis />
                                <Tooltip />
                                <Line type="monotone" dataKey="cpu_usage" stroke="#8884d8" />
                              </LineChart>
                            </ResponsiveContainer>
                          </CardContent>
                        </Card>
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Memory />
                              Memory Usage Over Time
                            </Typography>
                            <ResponsiveContainer width="100%" height={300}>
                              <LineChart data={routerDetails.monitoring_data}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="timestamp" />
                                <YAxis />
                                <Tooltip />
                                <Line type="monotone" dataKey="memory_usage" stroke="#82ca9d" />
                              </LineChart>
                            </ResponsiveContainer>
                          </CardContent>
                        </Card>
                      </Grid>
                    </Grid>
                  ) : (
                    <Alert severity="info">No monitoring data available</Alert>
                  )}
                </Box>
              )}

              {tabValue === 2 && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Cable />
                    Network Interfaces
                  </Typography>
                  <Grid container spacing={2}>
                    {routerDetails.interfaces.map((iface, index) => (
                      <Grid item xs={12} md={6} lg={4} key={index}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              {getStatusIcon(iface.status)}
                              {iface.name}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Status: <Chip label={iface.status} size="small" color={getStatusColor(iface.status)} />
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              IP: {iface.ip_address || 'Not assigned'}
                            </Typography>
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}

              {tabValue === 3 && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <NetworkCheck />
                    Customer VLANs
                  </Typography>
                  <Grid container spacing={2}>
                    {routerDetails.customer_vlans.map((vlan, index) => (
                      <Grid item xs={12} md={6} lg={4} key={index}>
                        <Card variant="outlined">
                          <CardContent>
                            <Typography variant="subtitle1">
                              VLAN {vlan.vlan_id}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Customer ID: {vlan.customer_id}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Status: <Chip label={vlan.status} size="small" color={getStatusColor(vlan.status)} />
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Isolation: {vlan.isolation_enabled ? 'Enabled' : 'Disabled'}
                            </Typography>
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}
            </Box>
          ) : (
            <Alert severity="error">Failed to load router details</Alert>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default RouterManagement;