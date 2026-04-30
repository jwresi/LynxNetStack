import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Paper,
  Chip,
  Tab,
  Tabs,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { Add, Search, Person, PersonAdd, PauseCircle } from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import api from '../services/api';
import { Customer } from '../types';

function Customers() {
  const location = useLocation();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [addCustomerOpen, setAddCustomerOpen] = useState(false);
  const [newCustomer, setNewCustomer] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    service_plan_id: 1
  });

  // Determine page type based on route
  const getPageType = () => {
    if (location.pathname === '/customers/new') return 'new';
    if (location.pathname === '/customers/prospects') return 'prospects';
    if (location.pathname === '/customers/suspended') return 'suspended';
    return 'all';
  };

  const pageType = getPageType();

  useEffect(() => {
    const fetchCustomers = async () => {
      try {
        const params: any = {};
        if (searchTerm) params.search = searchTerm;
        
        // Filter based on page type
        if (pageType === 'suspended') params.status = 'suspended';
        if (pageType === 'prospects') params.status = 'prospect';
        
        const response = await api.get('/customers', { params });
        setCustomers(response.data);
      } catch (error) {
        console.error('Failed to fetch customers:', error);
      } finally {
        setLoading(false);
      }
    };

    if (pageType !== 'new') {
      fetchCustomers();
    } else {
      setLoading(false);
    }
  }, [searchTerm, pageType]);

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 90 },
    { field: 'name', headerName: 'Name', width: 200 },
    { field: 'email', headerName: 'Email', width: 250 },
    { field: 'phone', headerName: 'Phone', width: 150 },
    {
      field: 'service_plan',
      headerName: 'Service Plan',
      width: 200,
      valueGetter: (params) => params.row.service_plan?.name || 'N/A'
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 120,
      renderCell: (params) => (
        <Chip
          label={params.value}
          color={
            params.value === 'active' ? 'success' :
            params.value === 'suspended' ? 'warning' : 'default'
          }
          size="small"
        />
      )
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      renderCell: (params) => (
        <Button
          component={Link}
          to={`/customers/${params.row.id}`}
          variant="outlined"
          size="small"
        >
          View
        </Button>
      )
    }
  ];

  const getPageTitle = () => {
    switch (pageType) {
      case 'new': return 'Add New Customer';
      case 'prospects': return 'Customer Prospects';
      case 'suspended': return 'Suspended Customers';
      default: return 'All Customers';
    }
  };

  const getPageIcon = () => {
    switch (pageType) {
      case 'new': return <PersonAdd />;
      case 'prospects': return <Person />;
      case 'suspended': return <PauseCircle />;
      default: return <Person />;
    }
  };

  const handleCreateCustomer = async () => {
    try {
      await api.post('/customers', newCustomer);
      setAddCustomerOpen(false);
      setNewCustomer({ name: '', email: '', phone: '', address: '', service_plan_id: 1 });
      // Navigate back to customers list
      window.location.href = '/customers';
    } catch (error) {
      console.error('Failed to create customer:', error);
    }
  };

  if (pageType === 'new') {
    return (
      <Box>
        <Box display="flex" alignItems="center" mb={3}>
          <PersonAdd sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h4">Add New Customer</Typography>
        </Box>
        
        <Paper sx={{ p: 3, maxWidth: 600 }}>
          <Box display="flex" flexDirection="column" gap={3}>
            <TextField
              fullWidth
              label="Customer Name"
              value={newCustomer.name}
              onChange={(e) => setNewCustomer({ ...newCustomer, name: e.target.value })}
            />
            <TextField
              fullWidth
              label="Email Address"
              type="email"
              value={newCustomer.email}
              onChange={(e) => setNewCustomer({ ...newCustomer, email: e.target.value })}
            />
            <TextField
              fullWidth
              label="Phone Number"
              value={newCustomer.phone}
              onChange={(e) => setNewCustomer({ ...newCustomer, phone: e.target.value })}
            />
            <TextField
              fullWidth
              label="Address"
              multiline
              rows={3}
              value={newCustomer.address}
              onChange={(e) => setNewCustomer({ ...newCustomer, address: e.target.value })}
            />
            <FormControl fullWidth>
              <InputLabel>Service Plan</InputLabel>
              <Select
                value={newCustomer.service_plan_id}
                onChange={(e) => setNewCustomer({ ...newCustomer, service_plan_id: Number(e.target.value) })}
              >
                <MenuItem value={1}>Basic - $39.99</MenuItem>
                <MenuItem value={2}>Standard - $69.99</MenuItem>
                <MenuItem value={3}>Premium - $99.99</MenuItem>
                <MenuItem value={4}>Enterprise - $199.99</MenuItem>
              </Select>
            </FormControl>
            
            <Box display="flex" gap={2} pt={2}>
              <Button 
                variant="contained" 
                onClick={handleCreateCustomer}
                disabled={!newCustomer.name || !newCustomer.email}
              >
                Create Customer
              </Button>
              <Button 
                variant="outlined" 
                onClick={() => window.location.href = '/customers'}
              >
                Cancel
              </Button>
            </Box>
          </Box>
        </Paper>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box display="flex" alignItems="center">
          {getPageIcon()}
          <Typography variant="h4" sx={{ ml: 2 }}>{getPageTitle()}</Typography>
        </Box>
        {pageType === 'all' && (
          <Button 
            variant="contained" 
            startIcon={<Add />}
            onClick={() => window.location.href = '/customers/new'}
          >
            Add Customer
          </Button>
        )}
      </Box>

      <Box display="flex" gap={2} mb={3}>
        <TextField
          placeholder="Search customers..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
          }}
          sx={{ minWidth: 300 }}
        />
      </Box>

      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={customers}
          columns={columns}
          loading={loading}
          pageSizeOptions={[25, 50, 100]}
          initialState={{
            pagination: {
              paginationModel: { page: 0, pageSize: 25 }
            }
          }}
          disableRowSelectionOnClick
        />
      </Paper>
    </Box>
  );
}

export default Customers;