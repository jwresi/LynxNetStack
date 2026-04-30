import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
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
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  Alert,
  Avatar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  Checkbox,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Refresh,
  Group,
  AdminPanelSettings,
  Support,
  Build,
  Engineering,
  AccountBalance,
  PersonAdd,
  Security,
  ExpandMore,
  Visibility,
  VisibilityOff,
  Badge,
  Phone,
  Email,
  Work,
  CalendarToday,
  CheckCircle,
  Cancel,
  Warning,
  Shield
} from '@mui/icons-material';
import api from '../services/api';

interface User {
  id: number;
  username: string;
  email: string;
  role: string;
  first_name: string;
  last_name: string;
  phone: string;
  employee_id: string;
  department: string;
  hire_date: string;
  status: string;
  permissions: any;
  last_login: string;
  created_at: string;
}

interface Permission {
  id: string;
  name: string;
  description: string;
  module: string;
}

const roleDefinitions = {
  admin: {
    name: 'Administrator',
    description: 'Full system access and management',
    color: 'error',
    icon: <AdminPanelSettings />
  },
  customer_service: {
    name: 'Customer Service',
    description: 'Customer management and support',
    color: 'primary',
    icon: <Support />
  },
  installer: {
    name: 'Installer/Technician',
    description: 'Field installations and maintenance',
    color: 'info',
    icon: <Build />
  },
  contractor: {
    name: 'Contractor',
    description: 'External contractor access',
    color: 'warning',
    icon: <Engineering />
  },
  billing: {
    name: 'Billing Specialist',
    description: 'Billing and payment management',
    color: 'success',
    icon: <AccountBalance />
  },
  sales: {
    name: 'Sales Representative',
    description: 'Sales and lead management',
    color: 'secondary',
    icon: <PersonAdd />
  }
};

const modulePermissions: Permission[] = [
  // Customer Management
  { id: 'customers.view', name: 'View Customers', description: 'View customer information', module: 'customers' },
  { id: 'customers.create', name: 'Create Customers', description: 'Add new customers', module: 'customers' },
  { id: 'customers.edit', name: 'Edit Customers', description: 'Modify customer information', module: 'customers' },
  { id: 'customers.delete', name: 'Delete Customers', description: 'Remove customers', module: 'customers' },
  
  // Network Management
  { id: 'network.view', name: 'View Network', description: 'View network topology and equipment', module: 'network' },
  { id: 'network.configure', name: 'Configure Network', description: 'Configure routers and equipment', module: 'network' },
  { id: 'network.monitor', name: 'Monitor Network', description: 'Access monitoring data', module: 'network' },
  
  // Billing
  { id: 'billing.view', name: 'View Billing', description: 'View invoices and payments', module: 'billing' },
  { id: 'billing.create', name: 'Create Invoices', description: 'Generate invoices', module: 'billing' },
  { id: 'billing.process_payments', name: 'Process Payments', description: 'Process customer payments', module: 'billing' },
  
  // User Management
  { id: 'users.view', name: 'View Users', description: 'View user accounts', module: 'users' },
  { id: 'users.create', name: 'Create Users', description: 'Add new user accounts', module: 'users' },
  { id: 'users.edit', name: 'Edit Users', description: 'Modify user accounts', module: 'users' },
  { id: 'users.delete', name: 'Delete Users', description: 'Remove user accounts', module: 'users' },
  
  // Reports
  { id: 'reports.view', name: 'View Reports', description: 'Access reports and analytics', module: 'reports' },
  { id: 'reports.export', name: 'Export Reports', description: 'Export report data', module: 'reports' },
];

const UserManagement: React.FC = () => {
  const location = useLocation();
  const currentRoute = location.pathname;
  
  const [users, setUsers] = useState<User[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [permissionsDialogOpen, setPermissionsDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const [newUser, setNewUser] = useState({
    username: '',
    email: '',
    password: '',
    role: 'customer_service',
    first_name: '',
    last_name: '',
    phone: '',
    employee_id: '',
    department: '',
    status: 'active'
  });

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await api.get('/api/v1/auth/users');
      setUsers(response.data);
    } catch (error) {
      console.error('Failed to fetch users:', error);
      // Set empty array if API fails for now
      setUsers([]);
    }
  };

  const handleCreateUser = async () => {
    setLoading(true);
    try {
      await api.post('/api/v1/auth/users', {
        ...newUser,
        permissions: selectedPermissions
      });
      setNewUser({
        username: '',
        email: '',
        password: '',
        role: 'customer_service',
        first_name: '',
        last_name: '',
        phone: '',
        employee_id: '',
        department: '',
        status: 'active'
      });
      setSelectedPermissions([]);
      setDialogOpen(false);
      fetchUsers();
    } catch (error) {
      console.error('Failed to create user:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (userId: number) => {
    if (window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      try {
        await api.delete(`/api/v1/auth/users/${userId}`);
        fetchUsers();
      } catch (error) {
        console.error('Failed to delete user:', error);
      }
    }
  };

  const handleUpdatePermissions = async () => {
    if (!editingUser) return;
    
    setLoading(true);
    try {
      await api.put(`/api/v1/auth/users/${editingUser.id}`, {
        permissions: selectedPermissions
      });
      setPermissionsDialogOpen(false);
      setEditingUser(null);
      fetchUsers();
    } catch (error) {
      console.error('Failed to update user permissions:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'success';
      case 'inactive':
        return 'default';
      case 'suspended':
        return 'error';
      default:
        return 'default';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active':
        return <CheckCircle color="success" />;
      case 'inactive':
        return <Cancel color="disabled" />;
      case 'suspended':
        return <Warning color="error" />;
      default:
        return <Cancel />;
    }
  };

  const getRoleInfo = (role: string) => {
    return roleDefinitions[role as keyof typeof roleDefinitions] || {
      name: role,
      description: 'Custom role',
      color: 'default',
      icon: <Group />
    };
  };

  const handlePermissionToggle = (permissionId: string) => {
    setSelectedPermissions(prev => 
      prev.includes(permissionId)
        ? prev.filter(id => id !== permissionId)
        : [...prev, permissionId]
    );
  };

  const getPermissionsByModule = () => {
    const modules = ['customers', 'network', 'billing', 'users', 'reports'];
    return modules.map(module => ({
      module,
      permissions: modulePermissions.filter(p => p.module === module)
    }));
  };

  const getCurrentPageInfo = () => {
    if (currentRoute === '/roles') {
      return {
        title: 'Roles & Permissions',
        icon: <Shield />,
        description: 'Manage user roles and permissions'
      };
    }
    return {
      title: 'User Management',
      icon: <Group />,
      description: 'Manage user accounts and access'
    };
  };

  const isUsersRoute = currentRoute === '/users';
  const isRolesRoute = currentRoute === '/roles';

  const pageInfo = getCurrentPageInfo();

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {pageInfo.icon}
            {pageInfo.title}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {pageInfo.description}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchUsers}
          >
            Refresh
          </Button>
          {isUsersRoute && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setDialogOpen(true)}
            >
              Add User
            </Button>
          )}
          {isRolesRoute && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setDialogOpen(true)}
            >
              Add Role
            </Button>
          )}
        </Box>
      </Box>

      {isUsersRoute && (
        <>
          <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
            <Tab label="All Users" />
            <Tab label="Administrators" />
            <Tab label="Customer Service" />
            <Tab label="Installers" />
            <Tab label="Billing" />
            <Tab label="Contractors" />
          </Tabs>

          {/* User Statistics Cards */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <AdminPanelSettings color="error" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {users.filter(u => u.role === 'admin').length}
                      </Typography>
                      <Typography color="text.secondary">Administrators</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Support color="primary" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {users.filter(u => u.role === 'customer_service').length}
                      </Typography>
                      <Typography color="text.secondary">Customer Service</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Build color="info" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {users.filter(u => u.role === 'installer').length}
                      </Typography>
                      <Typography color="text.secondary">Installers</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <CheckCircle color="success" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {users.filter(u => u.status === 'active').length}
                      </Typography>
                      <Typography color="text.secondary">Active Users</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Users Table */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                User Accounts ({users.length})
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>User</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Department</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Last Login</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {users
                      .filter(user => 
                        tabValue === 0 || 
                        (tabValue === 1 && user.role === 'admin') ||
                        (tabValue === 2 && user.role === 'customer_service') ||
                        (tabValue === 3 && user.role === 'installer') ||
                        (tabValue === 4 && user.role === 'billing') ||
                        (tabValue === 5 && user.role === 'contractor')
                      )
                      .map((user) => {
                        const roleInfo = getRoleInfo(user.role);
                        return (
                          <TableRow key={user.id}>
                            <TableCell>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                <Avatar sx={{ bgcolor: `${roleInfo.color}.main` }}>
                                  {user.first_name?.[0] || user.username[0]}
                                </Avatar>
                                <Box>
                                  <Typography variant="subtitle2">
                                    {user.first_name} {user.last_name}
                                  </Typography>
                                  <Typography variant="body2" color="text.secondary">
                                    {user.username} • {user.email}
                                  </Typography>
                                  {user.employee_id && (
                                    <Typography variant="caption" color="text.secondary">
                                      ID: {user.employee_id}
                                    </Typography>
                                  )}
                                </Box>
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                {roleInfo.icon}
                                <Box>
                                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                    {roleInfo.name}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {roleInfo.description}
                                  </Typography>
                                </Box>
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">
                                {user.department || 'Not assigned'}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                {getStatusIcon(user.status)}
                                <Chip 
                                  label={user.status} 
                                  color={getStatusColor(user.status)}
                                  size="small"
                                />
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">
                                {user.last_login ? 
                                  new Date(user.last_login).toLocaleDateString() : 
                                  'Never'
                                }
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: 'flex', gap: 1 }}>
                                <IconButton 
                                  size="small" 
                                  color="primary"
                                  onClick={() => {
                                    setEditingUser(user);
                                    setDialogOpen(true);
                                  }}
                                >
                                  <Edit />
                                </IconButton>
                                <IconButton 
                                  size="small" 
                                  color="info"
                                  onClick={() => {
                                    setEditingUser(user);
                                    setSelectedPermissions(user.permissions || []);
                                    setPermissionsDialogOpen(true);
                                  }}
                                >
                                  <Security />
                                </IconButton>
                                <IconButton 
                                  size="small" 
                                  color="error"
                                  onClick={() => handleDeleteUser(user.id)}
                                >
                                  <Delete />
                                </IconButton>
                              </Box>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </>
      )}

      {isRolesRoute && (
        <>
          {/* Role Statistics Cards */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Shield color="primary" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {Object.keys(roleDefinitions).length}
                      </Typography>
                      <Typography color="text.secondary">Total Roles</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Security color="info" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {modulePermissions.length}
                      </Typography>
                      <Typography color="text.secondary">Permissions</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <AdminPanelSettings color="warning" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {users.filter(u => u.role === 'admin').length}
                      </Typography>
                      <Typography color="text.secondary">Admin Users</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Group color="success" sx={{ fontSize: 40 }} />
                    <Box>
                      <Typography variant="h4">
                        {new Set(modulePermissions.map(p => p.module)).size}
                      </Typography>
                      <Typography color="text.secondary">Modules</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Roles Management */}
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Shield />
                    System Roles
                  </Typography>
                  <List>
                    {Object.entries(roleDefinitions).map(([key, role]) => (
                      <ListItem key={key} divider>
                        <ListItemIcon>
                          {role.icon}
                        </ListItemIcon>
                        <ListItemText
                          primary={role.name}
                          secondary={role.description}
                        />
                        <ListItemSecondaryAction>
                          <Box sx={{ display: 'flex', gap: 1 }}>
                            <Chip 
                              label={`${users.filter(u => u.role === key).length} users`}
                              size="small"
                              color={role.color as any}
                            />
                            <IconButton size="small" color="primary">
                              <Edit />
                            </IconButton>
                          </Box>
                        </ListItemSecondaryAction>
                      </ListItem>
                    ))}
                  </List>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Security />
                    Permission Modules
                  </Typography>
                  {getPermissionsByModule().map(({ module, permissions }) => (
                    <Accordion key={module} sx={{ mb: 1 }}>
                      <AccordionSummary expandIcon={<ExpandMore />}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                          <Typography variant="subtitle1" sx={{ textTransform: 'capitalize', flex: 1 }}>
                            {module} Management
                          </Typography>
                          <Chip 
                            label={`${permissions.length} permissions`}
                            size="small"
                            color="primary"
                          />
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails>
                        <List dense>
                          {permissions.map((permission) => (
                            <ListItem key={permission.id}>
                              <ListItemIcon>
                                <Security fontSize="small" />
                              </ListItemIcon>
                              <ListItemText
                                primary={permission.name}
                                secondary={permission.description}
                              />
                            </ListItem>
                          ))}
                        </List>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </>
      )}

      {/* Create/Edit User Dialog */}
      <Dialog 
        open={dialogOpen} 
        onClose={() => {
          setDialogOpen(false);
          setEditingUser(null);
        }} 
        maxWidth="md" 
        fullWidth
      >
        <DialogTitle>
          {editingUser ? 'Edit User' : 'Create New User'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Username"
                value={newUser.username}
                onChange={(e) => setNewUser({...newUser, username: e.target.value})}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Email"
                type="email"
                value={newUser.email}
                onChange={(e) => setNewUser({...newUser, email: e.target.value})}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="First Name"
                value={newUser.first_name}
                onChange={(e) => setNewUser({...newUser, first_name: e.target.value})}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Last Name"
                value={newUser.last_name}
                onChange={(e) => setNewUser({...newUser, last_name: e.target.value})}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Phone"
                value={newUser.phone}
                onChange={(e) => setNewUser({...newUser, phone: e.target.value})}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Employee ID"
                value={newUser.employee_id}
                onChange={(e) => setNewUser({...newUser, employee_id: e.target.value})}
                margin="normal"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth margin="normal">
                <InputLabel>Role</InputLabel>
                <Select
                  value={newUser.role}
                  onChange={(e) => setNewUser({...newUser, role: e.target.value})}
                  label="Role"
                >
                  {Object.entries(roleDefinitions).map(([key, role]) => (
                    <MenuItem key={key} value={key}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {role.icon}
                        {role.name}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Department"
                value={newUser.department}
                onChange={(e) => setNewUser({...newUser, department: e.target.value})}
                margin="normal"
              />
            </Grid>
            {!editingUser && (
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Password"
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({...newUser, password: e.target.value})}
                  margin="normal"
                />
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setDialogOpen(false);
            setEditingUser(null);
          }}>
            Cancel
          </Button>
          <Button 
            onClick={handleCreateUser} 
            variant="contained"
            disabled={loading || !newUser.username || !newUser.email}
          >
            {editingUser ? 'Update User' : 'Create User'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Permissions Dialog */}
      <Dialog 
        open={permissionsDialogOpen} 
        onClose={() => setPermissionsDialogOpen(false)}
        maxWidth="md" 
        fullWidth
      >
        <DialogTitle>
          Manage Permissions - {editingUser?.first_name} {editingUser?.last_name}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            {getPermissionsByModule().map(({ module, permissions }) => (
              <Accordion key={module}>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="h6" sx={{ textTransform: 'capitalize' }}>
                    {module} Management
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <List>
                    {permissions.map((permission) => (
                      <ListItem key={permission.id} dense>
                        <ListItemIcon>
                          <Checkbox
                            checked={selectedPermissions.includes(permission.id)}
                            onChange={() => handlePermissionToggle(permission.id)}
                          />
                        </ListItemIcon>
                        <ListItemText
                          primary={permission.name}
                          secondary={permission.description}
                        />
                      </ListItem>
                    ))}
                  </List>
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPermissionsDialogOpen(false)}>
            Cancel
          </Button>
          <Button 
            variant="contained"
            onClick={handleUpdatePermissions}
            disabled={loading}
          >
            Save Permissions
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default UserManagement;