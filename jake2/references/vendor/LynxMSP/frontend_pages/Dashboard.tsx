import React, { useState, useEffect } from 'react';
import {
  Grid,
  Paper,
  Typography,
  Box,
  Card,
  CardContent,
  LinearProgress,
  Chip,
  IconButton,
  Alert,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction
} from '@mui/material';
import {
  People,
  AttachMoney,
  Receipt,
  Support,
  Router as RouterIcon,
  NetworkCheck,
  Speed,
  Memory,
  Refresh,
  CheckCircle,
  Warning,
  Error,
  Info,
  Business
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  AreaChart,
  Area
} from 'recharts';
import api from '../services/api';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];

interface DashboardStats {
  total_customers: number;
  active_customers: number;
  total_sites: number;
  active_routers: number;
  pending_orders: number;
  open_tickets: number;
  monthly_revenue: number;
  network_utilization: number;
  cgnat_pools: number;
  cgnat_allocations: number;
  ipv6_pools: number;
  ipv6_delegations: number;
}

interface NetworkOverview {
  sites: Array<{
    id: number;
    name: string;
    location: string;
    type: string;
    routers: number;
    customers: number;
    status: string;
  }>;
}

function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [networkOverview, setNetworkOverview] = useState<NetworkOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsResponse, networkResponse, revenueResponse, utilizationResponse] = await Promise.all([
          api.get('/dashboard/stats'),
          api.get('/dashboard/network-overview'),
          api.get('/dashboard/revenue-chart').catch(() => ({ data: [] })), // Fallback to empty array if endpoint doesn't exist
          api.get('/dashboard/network-utilization').catch(() => ({ data: [] })) // Fallback to empty array if endpoint doesn't exist
        ]);
        setStats(statsResponse.data);
        setNetworkOverview(networkResponse.data);
        setRevenueData(revenueResponse.data);
        setNetworkUtilizationData(utilizationResponse.data);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
        // Set empty arrays for chart data if API calls fail
        setRevenueData([]);
        setNetworkUtilizationData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // Dynamic chart data from API
  const [revenueData, setRevenueData] = useState<Array<{month: string, revenue: number, customers: number}>>([]);
  const [networkUtilizationData, setNetworkUtilizationData] = useState<Array<{time: string, utilization: number, traffic: number}>>([]);

  const customerStatusData = [
    { name: 'Active', value: stats?.active_customers || 0, color: '#00C49F' },
    { name: 'Inactive', value: (stats?.total_customers || 0) - (stats?.active_customers || 0), color: '#FF8042' },
  ];

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

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <Typography>Loading dashboard...</Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">
          LynxCRM Dashboard
        </Typography>
        <IconButton onClick={() => window.location.reload()}>
          <Refresh />
        </IconButton>
      </Box>

      <Grid container spacing={3}>
        {/* Core Business Stats */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <People color="primary" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    Total Customers
                  </Typography>
                  <Typography variant="h4">
                    {stats?.total_customers || 0}
                  </Typography>
                  <Typography variant="body2" color="success.main">
                    {stats?.active_customers || 0} active
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <AttachMoney color="success" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    Monthly Revenue
                  </Typography>
                  <Typography variant="h4">
                    ${stats?.monthly_revenue?.toLocaleString() || 0}
                  </Typography>
                  <Typography variant="body2" color="success.main">
                    +8.2% from last month
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <RouterIcon color="info" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    Active Routers
                  </Typography>
                  <Typography variant="h4">
                    {stats?.active_routers || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    of {stats?.total_sites || 0} sites
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <NetworkCheck color="warning" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    Network Utilization
                  </Typography>
                  <Typography variant="h4">
                    {stats?.network_utilization || 0}%
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={stats?.network_utilization || 0} 
                    sx={{ mt: 1 }}
                  />
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Network Infrastructure Stats */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Speed color="primary" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    CGNAT Pools
                  </Typography>
                  <Typography variant="h4">
                    {stats?.cgnat_pools || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {stats?.cgnat_allocations || 0} allocations
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Memory color="secondary" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    IPv6 Pools
                  </Typography>
                  <Typography variant="h4">
                    {stats?.ipv6_pools || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {stats?.ipv6_delegations || 0} delegations
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Receipt color="warning" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    Service Orders
                  </Typography>
                  <Typography variant="h4">
                    {stats?.pending_orders || 0}
                  </Typography>
                  <Typography variant="body2" color="warning.main">
                    pending
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Support color="error" sx={{ mr: 2 }} />
                <Box>
                  <Typography color="text.secondary" variant="h6">
                    Open Tickets
                  </Typography>
                  <Typography variant="h4">
                    {stats?.open_tickets || 0}
                  </Typography>
                  <Typography variant="body2" color="error.main">
                    require attention
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Network Overview */}
        <Grid item xs={12} lg={8}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Business />
              Site Network Overview
            </Typography>
            {networkOverview && networkOverview.sites.length > 0 ? (
              <Grid container spacing={2}>
                {networkOverview.sites.map((site) => (
                  <Grid item xs={12} md={6} key={site.id}>
                    <Card variant="outlined">
                      <CardContent sx={{ py: 2 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                            {site.name}
                          </Typography>
                          <Chip 
                            label={site.status} 
                            color={getStatusColor(site.status)}
                            size="small"
                          />
                        </Box>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          {site.location} • {site.type}
                        </Typography>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                          <Typography variant="body2">
                            <RouterIcon fontSize="small" sx={{ mr: 0.5, verticalAlign: 'middle' }} />
                            {site.routers} Routers
                          </Typography>
                          <Typography variant="body2">
                            <People fontSize="small" sx={{ mr: 0.5, verticalAlign: 'middle' }} />
                            {site.customers} Customers
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            ) : (
              <Alert severity="info">No sites configured yet</Alert>
            )}
          </Paper>
        </Grid>

        {/* Customer Status Chart */}
        <Grid item xs={12} lg={4}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Customer Status Distribution
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={customerStatusData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {customerStatusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Revenue and Growth Chart */}
        <Grid item xs={12} lg={8}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Revenue & Customer Growth
            </Typography>
            <ResponsiveContainer width="100%" height={350}>
              <AreaChart data={revenueData}>
                <defs>
                  <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8884d8" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#8884d8" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorCustomers" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#82ca9d" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#82ca9d" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" />
                <Tooltip 
                  formatter={(value, name) => [
                    name === 'revenue' ? `$${value}` : value,
                    name === 'revenue' ? 'Revenue' : 'Customers'
                  ]} 
                />
                <Area 
                  yAxisId="left"
                  type="monotone" 
                  dataKey="revenue" 
                  stroke="#8884d8" 
                  fillOpacity={1} 
                  fill="url(#colorRevenue)" 
                />
                <Area 
                  yAxisId="right"
                  type="monotone" 
                  dataKey="customers" 
                  stroke="#82ca9d" 
                  fillOpacity={1} 
                  fill="url(#colorCustomers)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Network Utilization Chart */}
        <Grid item xs={12} lg={4}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Network Utilization (24h)
            </Typography>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={networkUtilizationData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip formatter={(value, name) => [`${value}${name === 'utilization' ? '%' : ' Gbps'}`, name === 'utilization' ? 'Utilization' : 'Traffic']} />
                <Bar dataKey="utilization" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}

export default Dashboard;