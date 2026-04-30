/**
 * Unified Real-Time Monitoring Dashboard
 * Integrates data from Splynx, Mikrotik, and TPLink TUAC APIs
 */

import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Button,
  Chip,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  NetworkCheck,
  People,
  Router,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Refresh,
  Settings,
  Visibility,
  Speed,
  Memory,
  DeviceHub,
  SignalWifi4Bar,
  MonitorHeart,
  TrendingUp,
  TrendingDown,
  Assignment,
  Schedule,
  Today,
  CalendarMonth,
  Notifications,
  WbSunny,
  NightsStay,
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as ChartTooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';

import UnifiedNetworkAPI, { UnifiedDevice, UnifiedCustomer, MonitoringData } from '../services/unifiedNetworkAPI';
import { createSplynxConfig } from '../services/splynxAPI';
import { createMikrotikConfig } from '../services/mikrotikAPI';
import { createTUACConfig } from '../services/tplinkTUACAPI';
import { useAuth } from '../hooks/useAuth';

interface DashboardMetrics {
  network: {
    totalDevices: number;
    onlineDevices: number;
    offlineDevices: number;
    healthScore: number;
    totalBandwidth: number;
    usedBandwidth: number;
  };
  customers: {
    total: number;
    active: number;
    online: number;
    suspended: number;
    newToday: number;
  };
  services: {
    internet: number;
    voice: number;
    active: number;
    suspended: number;
  };
  billing: {
    monthlyRevenue: number;
    unpaidInvoices: number;
    overdueAmount: number;
    collectionRate: number;
  };
  system: {
    cpuUsage: number;
    memoryUsage: number;
    diskUsage: number;
    uptime: string;
  };
}

interface AlertItem {
  id: string;
  type: 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: Date;
  deviceId?: string;
  customerId?: string;
  resolved: boolean;
}

const CHART_COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7c7c', '#8dd1e1'];

interface DailyTask {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  category: 'network' | 'customer' | 'billing' | 'maintenance';
  dueTime: string;
  completed: boolean;
}

const UnifiedDashboard: React.FC = () => {
  const { user } = useAuth();
  const [unifiedAPI] = useState(() => {
    const splynxConfig = createSplynxConfig('development');
    const mikrotikConfig = createMikrotikConfig('development');
    const tuacConfig = createTUACConfig('development');
    return new UnifiedNetworkAPI(splynxConfig, [mikrotikConfig], [tuacConfig]);
  });

  const [metrics, setMetrics] = useState<DashboardMetrics>({
    network: { totalDevices: 0, onlineDevices: 0, offlineDevices: 0, healthScore: 0, totalBandwidth: 0, usedBandwidth: 0 },
    customers: { total: 0, active: 0, online: 0, suspended: 0, newToday: 0 },
    services: { internet: 0, voice: 0, active: 0, suspended: 0 },
    billing: { monthlyRevenue: 0, unpaidInvoices: 0, overdueAmount: 0, collectionRate: 0 },
    system: { cpuUsage: 0, memoryUsage: 0, diskUsage: 0, uptime: '' },
  });

  const [devices, setDevices] = useState<UnifiedDevice[]>([]);
  const [customers, setCustomers] = useState<UnifiedCustomer[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [monitoringData, setMonitoringData] = useState<MonitoringData[]>([]);
  const [chartData, setChartData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDevice, setSelectedDevice] = useState<UnifiedDevice | null>(null);
  const [deviceDetailsOpen, setDeviceDetailsOpen] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [dailyTasks, setDailyTasks] = useState<DailyTask[]>([
    {
      id: '1',
      title: 'Check Network Health',
      description: 'Verify all routers and switches are online',
      priority: 'high',
      category: 'network',
      dueTime: '09:00',
      completed: false
    },
    {
      id: '2', 
      title: 'Review Support Tickets',
      description: 'Address high priority customer issues',
      priority: 'high',
      category: 'customer',
      dueTime: '10:00',
      completed: false
    },
    {
      id: '3',
      title: 'Process Pending Invoices',
      description: 'Send out monthly billing statements',
      priority: 'medium',
      category: 'billing', 
      dueTime: '14:00',
      completed: false
    },
    {
      id: '4',
      title: 'Backup System Configuration',
      description: 'Create daily backup of router configs',
      priority: 'medium',
      category: 'maintenance',
      dueTime: '17:00',
      completed: false
    }
  ]);

  // Initialize dashboard data
  const initializeDashboard = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadDevices(),
        loadCustomers(),
        loadMonitoringData(),
        loadAlerts(),
      ]);
    } catch (error) {
      console.error('Failed to initialize dashboard:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDevices = async () => {
    try {
      const discoveredDevices = await unifiedAPI.discoverAllDevices();
      setDevices(discoveredDevices);
      
      // Update network metrics
      setMetrics(prev => ({
        ...prev,
        network: {
          ...prev.network,
          totalDevices: discoveredDevices.length,
          onlineDevices: discoveredDevices.filter(d => d.status === 'online').length,
          offlineDevices: discoveredDevices.filter(d => d.status === 'offline').length,
          healthScore: calculateNetworkHealth(discoveredDevices),
        },
      }));
    } catch (error) {
      console.error('Failed to load devices:', error);
      setDevices([]);
      setMetrics(prev => ({
        ...prev,
        network: {
          totalDevices: 0,
          onlineDevices: 0,
          offlineDevices: 0,
          healthScore: 0,
          totalBandwidth: 0,
          usedBandwidth: 0,
        },
      }));
    }
  };

  const loadCustomers = async () => {
    try {
      const unifiedCustomers = await unifiedAPI.getUnifiedCustomers({ limit: 100 });
      setCustomers(unifiedCustomers);
      
      // Update customer metrics
      setMetrics(prev => ({
        ...prev,
        customers: {
          total: unifiedCustomers.length,
          active: unifiedCustomers.filter(c => c.status === 'active').length,
          online: unifiedCustomers.filter(c => c.networkInfo.onlineStatus).length,
          suspended: unifiedCustomers.filter(c => c.status === 'suspended').length,
          newToday: unifiedCustomers.filter(c => {
            // This would need proper date comparison
            return false;
          }).length,
        },
      }));
    } catch (error) {
      console.error('Failed to load customers:', error);
      setCustomers([]);
      setMetrics(prev => ({
        ...prev,
        customers: {
          total: 0,
          active: 0,
          online: 0,
          suspended: 0,
          newToday: 0,
        },
        billing: {
          monthlyRevenue: 0,
          unpaidInvoices: 0,
          overdueAmount: 0,
          collectionRate: 0,
        },
        services: {
          internet: 0,
          voice: 0,
          active: 0,
          suspended: 0,
        },
      }));
    }
  };

  const loadMonitoringData = async () => {
    try {
      const monitoring = await unifiedAPI.getMonitoringData();
      setMonitoringData(monitoring);
      
      // Generate chart data from monitoring
      const chartData = generateChartData(monitoring);
      setChartData(chartData);
      
      // Update system metrics
      if (monitoring.length > 0) {
        const latestData = monitoring[monitoring.length - 1];
        setMetrics(prev => ({
          ...prev,
          system: {
            cpuUsage: latestData.metrics.device.cpuUsage,
            memoryUsage: latestData.metrics.device.memoryUsage,
            diskUsage: (latestData.metrics.device as any).diskUsage || 0,
            uptime: formatUptime(latestData.metrics.device.uptime),
          },
        }));
      }
    } catch (error) {
      console.error('Failed to load monitoring data:', error);
      setMonitoringData([]);
      setChartData([]);
      setMetrics(prev => ({
        ...prev,
        system: {
          cpuUsage: 0,
          memoryUsage: 0,
          diskUsage: 0,
          uptime: 'Unknown',
        },
      }));
    }
  };

  // Load real alerts from API
  const loadAlerts = async () => {
    try {
      const response = await api.get('/alerts');
      setAlerts(response.data);
    } catch (error) {
      console.error('Failed to load alerts:', error);
      setAlerts([]);
    }
  };

  // Auto-refresh functionality
  useEffect(() => {
    const interval = setInterval(() => {
      if (autoRefresh) {
        loadMonitoringData();
      }
    }, 30000); // Refresh every 30 seconds

    return () => clearInterval(interval);
  }, [autoRefresh]);

  useEffect(() => {
    initializeDashboard();
  }, [initializeDashboard]);

  // Helper functions
  const calculateNetworkHealth = (devices: UnifiedDevice[]): number => {
    if (devices.length === 0) return 0;
    const onlineDevices = devices.filter(d => d.status === 'online').length;
    return Math.round((onlineDevices / devices.length) * 100);
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  const generateChartData = (monitoring: MonitoringData[]): any[] => {
    return monitoring.map(item => ({
      time: item.timestamp,
      value: (item as any).value || 0
    }));
  };

  const getGreeting = (): string => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  };

  const getGreetingIcon = () => {
    const hour = new Date().getHours();
    if (hour < 12 || hour >= 18) return <WbSunny sx={{ color: '#ff9800' }} />;
    return <NightsStay sx={{ color: '#2196f3' }} />;
  };

  const toggleTaskCompleted = (taskId: string) => {
    setDailyTasks(prev => prev.map(task => 
      task.id === taskId ? { ...task, completed: !task.completed } : task
    ));
  };

  const getTaskPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'info';
      default: return 'default';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'network': return <NetworkCheck />;
      case 'customer': return <People />;
      case 'billing': return <Assessment />;
      case 'maintenance': return <Settings />;
      default: return <Assignment />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': case 'active': return 'success';
      case 'offline': case 'error': return 'error';
      case 'warning': return 'warning';
      default: return 'default';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'online': case 'active': return <CheckCircle color="success" />;
      case 'offline': case 'error': return <Error color="error" />;
      case 'warning': return <Warning color="warning" />;
      default: return <Error />;
    }
  };

  const handleDeviceClick = (device: UnifiedDevice) => {
    setSelectedDevice(device);
    setDeviceDetailsOpen(true);
  };

  const handleRefresh = () => {
    initializeDashboard();
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ ml: 2 }}>
          Loading unified dashboard...
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 0 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box display="flex" alignItems="center" gap={2}>
          <DashboardIcon sx={{ fontSize: 40, color: 'primary.main' }} />
          <Box>
            <Typography variant="h4">Unified Network Dashboard</Typography>
            <Typography variant="body2" color="text.secondary">
              Real-time monitoring across Splynx, Mikrotik, and TPLink TUAC
            </Typography>
          </Box>
        </Box>
        <Box display="flex" gap={1}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={handleRefresh}
          >
            Refresh
          </Button>
          <Button
            variant={autoRefresh ? 'contained' : 'outlined'}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            Auto Refresh
          </Button>
        </Box>
      </Box>

      {/* Welcome Section */}
      <Card sx={{ mb: 3, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
        <CardContent>
          <Grid container alignItems="center" spacing={2}>
            <Grid item>
              {getGreetingIcon()}
            </Grid>
            <Grid item xs>
              <Typography variant="h5">
                {getGreeting()}, {user?.username || 'Admin'}!
              </Typography>
              <Typography variant="body1" sx={{ opacity: 0.9 }}>
                Welcome back to your LynxMSP dashboard. Here's what needs your attention today.
              </Typography>
            </Grid>
            <Grid item>
              <Box textAlign="right">
                <Typography variant="h6">
                  {new Date().toLocaleDateString('en-US', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                  })}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>
                  {new Date().toLocaleTimeString('en-US', { 
                    hour: '2-digit', 
                    minute: '2-digit' 
                  })}
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Daily Tasks Summary */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2} mb={2}>
                <Today color="primary" />
                <Typography variant="h6">Today's Tasks</Typography>
                <Chip 
                  label={`${dailyTasks.filter(t => !t.completed).length} pending`} 
                  size="small" 
                  color={dailyTasks.filter(t => !t.completed).length > 0 ? 'warning' : 'success'}
                />
              </Box>
              <List dense>
                {dailyTasks.slice(0, 4).map((task) => (
                  <ListItem key={task.id} disablePadding>
                    <ListItemButton onClick={() => toggleTaskCompleted(task.id)}>
                      <ListItemIcon>
                        <CheckCircle color={task.completed ? 'success' : 'disabled'} />
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography 
                              variant="body2" 
                              sx={{ 
                                textDecoration: task.completed ? 'line-through' : 'none',
                                opacity: task.completed ? 0.6 : 1
                              }}
                            >
                              {task.title}
                            </Typography>
                            <Chip 
                              size="small" 
                              label={task.priority} 
                              color={getTaskPriorityColor(task.priority) as any}
                            />
                          </Box>
                        }
                        secondary={
                          <Box display="flex" alignItems="center" gap={1}>
                            {getCategoryIcon(task.category)}
                            <Typography variant="caption">
                              {task.dueTime} - {task.description}
                            </Typography>
                          </Box>
                        }
                      />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2} mb={2}>
                <CalendarMonth color="primary" />
                <Typography variant="h6">This Week's Overview</Typography>
              </Box>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="primary.main">
                      {metrics.customers.newToday}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      New Customers
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="success.main">
                      {metrics.billing.unpaidInvoices}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Open Tickets
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="warning.main">
                      {Math.round(metrics.network.healthScore)}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Network Health
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="info.main">
                      ${Math.round(metrics.billing.monthlyRevenue / 1000)}K
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Monthly Revenue
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Alert Banner */}
      {alerts.filter(a => !a.resolved).length > 0 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          {alerts.filter(a => !a.resolved).length} active alerts require attention
        </Alert>
      )}

      {/* Key Metrics Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <NetworkCheck color="primary" sx={{ fontSize: 40 }} />
                <Box>
                  <Typography variant="h4">{metrics.network.onlineDevices}/{metrics.network.totalDevices}</Typography>
                  <Typography color="text.secondary">Network Devices</Typography>
                  <LinearProgress
                    variant="determinate"
                    value={metrics.network.healthScore}
                    sx={{ mt: 1 }}
                  />
                  <Typography variant="caption">Health: {metrics.network.healthScore}%</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <People color="success" sx={{ fontSize: 40 }} />
                <Box>
                  <Typography variant="h4">{metrics.customers.online}</Typography>
                  <Typography color="text.secondary">Online Customers</Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    {metrics.customers.active} active / {metrics.customers.total} total
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <Assessment color="warning" sx={{ fontSize: 40 }} />
                <Box>
                  <Typography variant="h4">${metrics.billing.monthlyRevenue.toLocaleString()}</Typography>
                  <Typography color="text.secondary">Monthly Revenue</Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    {metrics.billing.unpaidInvoices} unpaid invoices
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <Speed color="info" sx={{ fontSize: 40 }} />
                <Box>
                  <Typography variant="h4">{metrics.network.usedBandwidth}M</Typography>
                  <Typography color="text.secondary">Bandwidth Usage</Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(metrics.network.usedBandwidth / metrics.network.totalBandwidth) * 100}
                    sx={{ mt: 1 }}
                  />
                  <Typography variant="caption">
                    {metrics.network.usedBandwidth}M / {metrics.network.totalBandwidth}M
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Charts and Analytics */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Network Performance (24h)</Typography>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" />
                  <YAxis />
                  <ChartTooltip />
                  <Line type="monotone" dataKey="bandwidth" stroke="#8884d8" name="Bandwidth (Mbps)" />
                  <Line type="monotone" dataKey="cpu" stroke="#82ca9d" name="CPU %" />
                  <Line type="monotone" dataKey="customers" stroke="#ffc658" name="Online Customers" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>System Health</Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2">CPU Usage</Typography>
                <LinearProgress variant="determinate" value={metrics.system.cpuUsage} />
                <Typography variant="caption">{metrics.system.cpuUsage}%</Typography>
              </Box>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2">Memory Usage</Typography>
                <LinearProgress variant="determinate" value={metrics.system.memoryUsage} />
                <Typography variant="caption">{metrics.system.memoryUsage}%</Typography>
              </Box>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2">Disk Usage</Typography>
                <LinearProgress variant="determinate" value={metrics.system.diskUsage} />
                <Typography variant="caption">{metrics.system.diskUsage}%</Typography>
              </Box>
              <Typography variant="body2">Uptime: {metrics.system.uptime}</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Device Status Table */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Network Devices</Typography>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Device</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>IP Address</TableCell>
                      <TableCell>Location</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {devices.map((device) => (
                      <TableRow key={device.id}>
                        <TableCell>
                          <Box>
                            <Typography variant="subtitle2">{device.name}</Typography>
                            <Typography variant="caption" color="text.secondary">
                              {device.model} • {device.firmwareVersion}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={device.type}
                            size="small"
                            color={device.type === 'mikrotik' ? 'primary' : device.type === 'tplink' ? 'secondary' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            {getStatusIcon(device.status)}
                            <Chip
                              label={device.status}
                              size="small"
                              color={getStatusColor(device.status)}
                            />
                          </Box>
                        </TableCell>
                        <TableCell>{device.ipAddress}</TableCell>
                        <TableCell>{device.location || 'Unknown'}</TableCell>
                        <TableCell>
                          <Tooltip title="View Details">
                            <IconButton size="small" onClick={() => handleDeviceClick(device)}>
                              <Visibility />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Settings">
                            <IconButton size="small">
                              <Settings />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Recent Alerts</Typography>
              <List>
                {alerts.slice(0, 5).map((alert) => (
                  <ListItem key={alert.id}>
                    <ListItemIcon>
                      {alert.type === 'error' ? (
                        <Error color="error" />
                      ) : alert.type === 'warning' ? (
                        <Warning color="warning" />
                      ) : (
                        <CheckCircle color="info" />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={alert.title}
                      secondary={
                        <span>
                          <div>{alert.message}</div>
                          <div style={{ fontSize: '0.75rem', color: 'rgba(0, 0, 0, 0.6)' }}>
                            {alert.timestamp.toLocaleString()}
                          </div>
                        </span>
                      }
                    />
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Device Details Dialog */}
      <Dialog open={deviceDetailsOpen} onClose={() => setDeviceDetailsOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedDevice?.name} Details
        </DialogTitle>
        <DialogContent>
          {selectedDevice && (
            <Box sx={{ pt: 2 }}>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="subtitle2">Type</Typography>
                  <Typography variant="body2">{selectedDevice.type}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="subtitle2">Status</Typography>
                  <Chip
                    label={selectedDevice.status}
                    size="small"
                    color={getStatusColor(selectedDevice.status)}
                  />
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="subtitle2">IP Address</Typography>
                  <Typography variant="body2">{selectedDevice.ipAddress}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="subtitle2">Model</Typography>
                  <Typography variant="body2">{selectedDevice.model}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="subtitle2">Firmware</Typography>
                  <Typography variant="body2">{selectedDevice.firmwareVersion}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="subtitle2">Last Seen</Typography>
                  <Typography variant="body2">{selectedDevice.lastSeen.toLocaleString()}</Typography>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="subtitle2">Capabilities</Typography>
                  <Box sx={{ mt: 1 }}>
                    {selectedDevice.capabilities.map((cap, index) => (
                      <Chip
                        key={index}
                        label={cap.type}
                        size="small"
                        color={cap.enabled ? 'success' : 'default'}
                        sx={{ mr: 1, mb: 1 }}
                      />
                    ))}
                  </Box>
                </Grid>
              </Grid>
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default UnifiedDashboard;