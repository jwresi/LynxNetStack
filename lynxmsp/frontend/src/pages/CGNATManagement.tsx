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
  LinearProgress,
  Alert,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Tooltip,
  CircularProgress
} from '@mui/material';
import {
  Router as RouterIcon,
  Add,
  Edit,
  Delete,
  Refresh,
  People,
  Settings,
  NetworkCheck,
  Assignment,
  Timeline,
  Info,
  Warning,
  CheckCircle,
  Error
} from '@mui/icons-material';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip } from 'recharts';
import api from '../services/api';

interface CGNATPool {
  id: number;
  name: string;
  public_ip_range: string;
  port_range: string;
  max_users: number;
  current_users: number;
  utilization: number;
  ports_per_user: number;
  status: string;
}

interface CGNATAllocation {
  id: number;
  pool_id: number;
  customer_id: number;
  port_range_start: number;
  port_range_end: number;
  status: string;
  created_at: string;
}

interface CGNATSession {
  id: number;
  customer_id: number;
  allocation_id: number;
  source_ip: string;
  source_port: number;
  destination_ip: string;
  destination_port: number;
  protocol: string;
  start_time: string;
  end_time?: string;
}

interface Customer {
  id: number;
  name: string;
  email: string;
}

const CGNATManagement: React.FC = () => {
  const [pools, setPools] = useState<CGNATPool[]>([]);
  const [allocations, setAllocations] = useState<CGNATAllocation[]>([]);
  const [sessions, setSessions] = useState<CGNATSession[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedPool, setSelectedPool] = useState<CGNATPool | null>(null);
  const [tabValue, setTabValue] = useState(0);
  const [poolDialogOpen, setPoolDialogOpen] = useState(false);
  const [allocationDialogOpen, setAllocationDialogOpen] = useState(false);
  const [editAllocationDialogOpen, setEditAllocationDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [selectedAllocation, setSelectedAllocation] = useState<CGNATAllocation | null>(null);
  const [editingPool, setEditingPool] = useState<CGNATPool | null>(null);
  const [poolToDelete, setPoolToDelete] = useState<{type: 'pool' | 'allocation', id: number, name: string} | null>(null);
  const [loading, setLoading] = useState(false);

  const [newPool, setNewPool] = useState({
    name: '',
    public_ip_range: '',
    port_range_start: 1024,
    port_range_end: 65535,
    max_users: 1000,
    ports_per_user: 64,
    status: 'active'
  });

  const [newAllocation, setNewAllocation] = useState({
    customer_id: '',
    pool_id: ''
  });

  const [editAllocationForm, setEditAllocationForm] = useState({
    status: '',
    port_range_start: 0,
    port_range_end: 0
  });

  useEffect(() => {
    fetchPools();
    fetchCustomers();
  }, []);

  const fetchPools = async () => {
    try {
      const response = await api.get('/cgnat/pools');
      setPools(response.data);
    } catch (error) {
      console.error('Failed to fetch CGNAT pools:', error);
    }
  };

  const fetchCustomers = async () => {
    try {
      const response = await api.get('/customers');
      setCustomers(response.data);
    } catch (error) {
      console.error('Failed to fetch customers:', error);
    }
  };

  const fetchAllocations = async (poolId?: number) => {
    try {
      const url = poolId ? `/cgnat/pools/${poolId}/allocations` : '/cgnat/allocations';
      const response = await api.get(url);
      setAllocations(response.data);
    } catch (error) {
      console.error('Failed to fetch allocations:', error);
    }
  };

  const fetchSessions = async () => {
    try {
      const response = await api.get('/cgnat/sessions');
      setSessions(response.data);
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const handleCreatePool = async () => {
    setLoading(true);
    try {
      if (editingPool) {
        await api.put(`/cgnat/pools/${editingPool.id}`, newPool);
      } else {
        await api.post('/cgnat/pools', newPool);
      }
      resetPoolForm();
      setPoolDialogOpen(false);
      setEditingPool(null);
      fetchPools();
    } catch (error) {
      console.error('Failed to save CGNAT pool:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEditPool = (pool: CGNATPool) => {
    setEditingPool(pool);
    setNewPool({
      name: pool.name,
      public_ip_range: pool.public_ip_range,
      port_range_start: 1024,
      port_range_end: 65535,
      max_users: pool.max_users,
      ports_per_user: pool.ports_per_user,
      status: pool.status
    });
    setPoolDialogOpen(true);
  };

  const handleDeletePool = (pool: CGNATPool) => {
    setPoolToDelete({
      type: 'pool',
      id: pool.id,
      name: pool.name
    });
    setDeleteDialogOpen(true);
  };

  const handleDeleteAllocation = (allocation: CGNATAllocation) => {
    setPoolToDelete({
      type: 'allocation',
      id: allocation.id,
      name: `Allocation ${allocation.id}`
    });
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!poolToDelete) return;
    
    setDeleteLoading(true);
    try {
      if (poolToDelete.type === 'pool') {
        await api.delete(`/cgnat/pools/${poolToDelete.id}`);
        fetchPools();
      } else {
        await api.delete(`/cgnat/allocations/${poolToDelete.id}`);
        fetchAllocations();
      }
      setDeleteDialogOpen(false);
      setPoolToDelete(null);
    } catch (error) {
      console.error(`Failed to delete CGNAT ${poolToDelete.type}:`, error);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCancelDelete = () => {
    setDeleteDialogOpen(false);
    setPoolToDelete(null);
  };

  const resetPoolForm = () => {
    setNewPool({
      name: '',
      public_ip_range: '',
      port_range_start: 1024,
      port_range_end: 65535,
      max_users: 1000,
      ports_per_user: 64,
      status: 'active'
    });
  };

  const handleAllocatePorts = async () => {
    setLoading(true);
    try {
      await api.post('/cgnat/allocate', {
        customer_id: parseInt(newAllocation.customer_id),
        pool_id: parseInt(newAllocation.pool_id)
      });
      setNewAllocation({ customer_id: '', pool_id: '' });
      setAllocationDialogOpen(false);
      fetchPools();
      fetchAllocations();
    } catch (error) {
      console.error('Failed to allocate CGNAT ports:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEditAllocation = (allocation: CGNATAllocation) => {
    setSelectedAllocation(allocation);
    setEditAllocationForm({
      status: allocation.status,
      port_range_start: allocation.port_range_start,
      port_range_end: allocation.port_range_end
    });
    setEditAllocationDialogOpen(true);
  };

  const handleSaveAllocationEdit = async () => {
    if (!selectedAllocation) return;
    
    setLoading(true);
    try {
      await api.put(`/cgnat/allocations/${selectedAllocation.id}`, editAllocationForm);
      setEditAllocationDialogOpen(false);
      setSelectedAllocation(null);
      fetchAllocations();
    } catch (error) {
      console.error('Failed to update CGNAT allocation:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelAllocationEdit = () => {
    setEditAllocationDialogOpen(false);
    setSelectedAllocation(null);
    setEditAllocationForm({
      status: '',
      port_range_start: 0,
      port_range_end: 0
    });
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
        return 'success';
      case 'inactive':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getUtilizationColor = (utilization: number) => {
    if (utilization < 70) return 'success';
    if (utilization < 90) return 'warning';
    return 'error';
  };

  const getCustomerName = (customerId: number) => {
    const customer = customers.find(c => c.id === customerId);
    return customer ? customer.name : `Customer ${customerId}`;
  };

  const utilizationData = pools.map(pool => ({
    name: pool.name,
    utilization: pool.utilization,
    current_users: pool.current_users,
    max_users: pool.max_users
  }));

  const pieData = pools.map(pool => ({
    name: pool.name,
    value: pool.current_users,
    color: pool.utilization > 80 ? '#ff4444' : pool.utilization > 60 ? '#ffaa00' : '#44ff44'
  }));

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <NetworkCheck />
          CGNAT Management
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchPools}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            startIcon={<Assignment />}
            onClick={() => setAllocationDialogOpen(true)}
          >
            Allocate Ports
          </Button>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setPoolDialogOpen(true)}
          >
            Create Pool
          </Button>
        </Box>
      </Box>

      <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <Tab label="Pools Overview" />
        <Tab label="Allocations" />
        <Tab label="Active Sessions" />
        <Tab label="Analytics" />
      </Tabs>

      {tabValue === 0 && (
        <Grid container spacing={3}>
          {/* Summary Cards */}
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>
                  Total Pools
                </Typography>
                <Typography variant="h3">{pools.length}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>
                  Active Users
                </Typography>
                <Typography variant="h3">
                  {pools.reduce((sum, pool) => sum + pool.current_users, 0)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>
                  Total Capacity
                </Typography>
                <Typography variant="h3">
                  {pools.reduce((sum, pool) => sum + pool.max_users, 0)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Typography variant="h6" color="primary" gutterBottom>
                  Avg. Utilization
                </Typography>
                <Typography variant="h3">
                  {pools.length > 0 ? Math.round(pools.reduce((sum, pool) => sum + pool.utilization, 0) / pools.length) : 0}%
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          {/* Pools Table */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  CGNAT Pools
                </Typography>
                <TableContainer component={Paper} variant="outlined">
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Pool Name</TableCell>
                        <TableCell>Public IP Range</TableCell>
                        <TableCell>Port Range</TableCell>
                        <TableCell>Users</TableCell>
                        <TableCell>Utilization</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {pools.map((pool) => (
                        <TableRow key={pool.id}>
                          <TableCell>
                            <Typography variant="subtitle2">{pool.name}</Typography>
                          </TableCell>
                          <TableCell>{pool.public_ip_range}</TableCell>
                          <TableCell>{pool.port_range}</TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <People fontSize="small" />
                              {pool.current_users} / {pool.max_users}
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <LinearProgress
                                variant="determinate"
                                value={pool.utilization}
                                color={getUtilizationColor(pool.utilization)}
                                sx={{ width: 100 }}
                              />
                              <Typography variant="body2">{pool.utilization}%</Typography>
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={pool.status}
                              color={getStatusColor(pool.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', gap: 1 }}>
                              <IconButton
                                size="small"
                                onClick={() => {
                                  setSelectedPool(pool);
                                  fetchAllocations(pool.id);
                                }}
                                title="View Details"
                              >
                                <Info />
                              </IconButton>
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={() => handleEditPool(pool)}
                                title="Edit Pool"
                              >
                                <Edit />
                              </IconButton>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => handleDeletePool(pool)}
                                title="Delete Pool"
                              >
                                <Delete />
                              </IconButton>
                            </Box>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tabValue === 1 && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6">Port Allocations</Typography>
                  <Button
                    variant="contained"
                    startIcon={<Assignment />}
                    onClick={() => {
                      setAllocationDialogOpen(true);
                      fetchAllocations();
                    }}
                  >
                    New Allocation
                  </Button>
                </Box>
                <TableContainer component={Paper} variant="outlined">
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Customer</TableCell>
                        <TableCell>Pool</TableCell>
                        <TableCell>Port Range</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Allocated</TableCell>
                        <TableCell>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {allocations.map((allocation) => (
                        <TableRow key={allocation.id}>
                          <TableCell>{getCustomerName(allocation.customer_id)}</TableCell>
                          <TableCell>
                            {pools.find(p => p.id === allocation.pool_id)?.name || 'Unknown Pool'}
                          </TableCell>
                          <TableCell>
                            {allocation.port_range_start} - {allocation.port_range_end}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={allocation.status}
                              color={getStatusColor(allocation.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            {new Date(allocation.created_at).toLocaleDateString()}
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', gap: 1 }}>
                              <IconButton 
                                size="small"
                                color="primary"
                                onClick={() => handleEditAllocation(allocation)}
                                title="Edit Allocation"
                              >
                                <Edit />
                              </IconButton>
                              <IconButton 
                                size="small"
                                color="error"
                                onClick={() => handleDeleteAllocation(allocation)}
                                title="Delete Allocation"
                              >
                                <Delete />
                              </IconButton>
                            </Box>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tabValue === 2 && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6">Active CGNAT Sessions</Typography>
                  <Button
                    variant="outlined"
                    startIcon={<Refresh />}
                    onClick={fetchSessions}
                  >
                    Refresh Sessions
                  </Button>
                </Box>
                <TableContainer component={Paper} variant="outlined">
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Customer</TableCell>
                        <TableCell>Source</TableCell>
                        <TableCell>Destination</TableCell>
                        <TableCell>Protocol</TableCell>
                        <TableCell>Started</TableCell>
                        <TableCell>Duration</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {sessions.slice(0, 100).map((session) => (
                        <TableRow key={session.id}>
                          <TableCell>{getCustomerName(session.customer_id)}</TableCell>
                          <TableCell>{session.source_ip}:{session.source_port}</TableCell>
                          <TableCell>{session.destination_ip}:{session.destination_port}</TableCell>
                          <TableCell>
                            <Chip label={session.protocol} size="small" variant="outlined" />
                          </TableCell>
                          <TableCell>
                            {new Date(session.start_time).toLocaleString()}
                          </TableCell>
                          <TableCell>
                            {session.end_time ? 
                              'Ended' : 
                              `${Math.round((Date.now() - new Date(session.start_time).getTime()) / 60000)}m`
                            }
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tabValue === 3 && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Pool Utilization</Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={utilizationData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <RechartsTooltip />
                    <Bar dataKey="utilization" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>User Distribution</Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({name, value}) => `${name}: ${value}`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Create Pool Dialog */}
      <Dialog open={poolDialogOpen} onClose={() => {setPoolDialogOpen(false); setEditingPool(null); resetPoolForm();}} maxWidth="md" fullWidth>
        <DialogTitle>{editingPool ? 'Edit CGNAT Pool' : 'Create CGNAT Pool'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Pool Name"
                value={newPool.name}
                onChange={(e) => setNewPool({...newPool, name: e.target.value})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Public IP Range"
                value={newPool.public_ip_range}
                onChange={(e) => setNewPool({...newPool, public_ip_range: e.target.value})}
                placeholder="e.g., 203.0.113.1-203.0.113.10"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Port Range Start"
                type="number"
                value={newPool.port_range_start}
                onChange={(e) => setNewPool({...newPool, port_range_start: parseInt(e.target.value)})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Port Range End"
                type="number"
                value={newPool.port_range_end}
                onChange={(e) => setNewPool({...newPool, port_range_end: parseInt(e.target.value)})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Max Users"
                type="number"
                value={newPool.max_users}
                onChange={(e) => setNewPool({...newPool, max_users: parseInt(e.target.value)})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Ports Per User"
                type="number"
                value={newPool.ports_per_user}
                onChange={(e) => setNewPool({...newPool, ports_per_user: parseInt(e.target.value)})}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {setPoolDialogOpen(false); setEditingPool(null); resetPoolForm();}}>Cancel</Button>
          <Button 
            onClick={handleCreatePool} 
            variant="contained"
            disabled={loading || !newPool.name || !newPool.public_ip_range}
          >
            {loading ? <CircularProgress size={20} /> : (editingPool ? 'Update Pool' : 'Create Pool')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Allocate Ports Dialog */}
      <Dialog open={allocationDialogOpen} onClose={() => setAllocationDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Allocate CGNAT Ports</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Customer</InputLabel>
                <Select
                  value={newAllocation.customer_id}
                  onChange={(e) => setNewAllocation({...newAllocation, customer_id: e.target.value})}
                  label="Customer"
                >
                  {customers.map((customer) => (
                    <MenuItem key={customer.id} value={customer.id}>
                      {customer.name} ({customer.email})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>CGNAT Pool</InputLabel>
                <Select
                  value={newAllocation.pool_id}
                  onChange={(e) => setNewAllocation({...newAllocation, pool_id: e.target.value})}
                  label="CGNAT Pool"
                >
                  {pools.map((pool) => (
                    <MenuItem key={pool.id} value={pool.id}>
                      {pool.name} ({pool.current_users}/{pool.max_users} users)
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAllocationDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleAllocatePorts} 
            variant="contained"
            disabled={loading || !newAllocation.customer_id || !newAllocation.pool_id}
          >
            {loading ? <CircularProgress size={20} /> : 'Allocate Ports'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Allocation Dialog */}
      <Dialog open={editAllocationDialogOpen} onClose={handleCancelAllocationEdit} maxWidth="sm" fullWidth>
        <DialogTitle>Edit CGNAT Allocation</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Customer ID"
                value={selectedAllocation?.customer_id || ''}
                disabled
                helperText="Customer ID cannot be changed"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={editAllocationForm.status}
                  onChange={(e) => setEditAllocationForm({...editAllocationForm, status: e.target.value})}
                  label="Status"
                >
                  <MenuItem value="active">Active</MenuItem>
                  <MenuItem value="inactive">Inactive</MenuItem>
                  <MenuItem value="suspended">Suspended</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                type="number"
                label="Port Range Start"
                value={editAllocationForm.port_range_start}
                onChange={(e) => setEditAllocationForm({
                  ...editAllocationForm, 
                  port_range_start: parseInt(e.target.value) || 0
                })}
                inputProps={{ min: 1024, max: 65535 }}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                type="number"
                label="Port Range End"
                value={editAllocationForm.port_range_end}
                onChange={(e) => setEditAllocationForm({
                  ...editAllocationForm, 
                  port_range_end: parseInt(e.target.value) || 0
                })}
                inputProps={{ min: 1024, max: 65535 }}
              />
            </Grid>
            <Grid item xs={12}>
              <Alert severity="info">
                Port range changes will affect the customer's connectivity. Ensure proper coordination before making changes.
              </Alert>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelAllocationEdit}>Cancel</Button>
          <Button 
            onClick={handleSaveAllocationEdit} 
            variant="contained"
            disabled={loading || !editAllocationForm.status || editAllocationForm.port_range_start >= editAllocationForm.port_range_end}
          >
            {loading ? <CircularProgress size={20} /> : 'Save Changes'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleCancelDelete} maxWidth="sm" fullWidth>
        <DialogTitle>Delete CGNAT {poolToDelete?.type}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. This may affect active connections and customer service.
          </Alert>
          <Typography>
            Are you sure you want to delete <strong>{poolToDelete?.name}</strong>?
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

export default CGNATManagement;