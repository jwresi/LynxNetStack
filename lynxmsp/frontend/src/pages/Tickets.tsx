import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Paper,
  Chip,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { 
  Add, 
  SupportAgent, 
  Build, 
  Engineering, 
  BusinessCenter 
} from '@mui/icons-material';
import api from '../services/api';
import { Ticket } from '../types';

function Tickets() {
  const location = useLocation();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');

  // Route configuration
  const getRouteConfig = () => {
    const path = location.pathname;
    
    if (path === '/tickets') {
      return {
        title: 'Support Tickets',
        icon: <SupportAgent />,
        apiEndpoint: '/tickets',
        buttonText: 'Create Ticket',
        type: 'tickets'
      };
    } else if (path === '/service-orders') {
      return {
        title: 'Service Orders',
        icon: <Build />,
        apiEndpoint: '/service-orders',
        buttonText: 'Create Service Order',
        type: 'service-orders'
      };
    } else if (path === '/installers') {
      return {
        title: 'Installers',
        icon: <Engineering />,
        apiEndpoint: '/installers',
        buttonText: 'Add Installer',
        type: 'installers'
      };
    } else if (path === '/contractors') {
      return {
        title: 'Contractors',
        icon: <BusinessCenter />,
        apiEndpoint: '/contractors',
        buttonText: 'Add Contractor',
        type: 'contractors'
      };
    }
    
    // Default fallback
    return {
      title: 'Support Tickets',
      icon: <SupportAgent />,
      apiEndpoint: '/tickets',
      buttonText: 'Create Ticket',
      type: 'tickets'
    };
  };

  const routeConfig = getRouteConfig();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await api.get(routeConfig.apiEndpoint);
        setTickets(response.data);
      } catch (error) {
        console.error(`Failed to fetch ${routeConfig.type}:`, error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [routeConfig.apiEndpoint, routeConfig.type]);

  const handleStatusUpdate = async (itemId: number, newStatus: string) => {
    try {
      let endpoint = '';
      if (routeConfig.type === 'tickets') {
        endpoint = `/tickets/${itemId}/status`;
      } else if (routeConfig.type === 'service-orders') {
        endpoint = `/service-orders/${itemId}/status`;
      } else if (routeConfig.type === 'installers') {
        endpoint = `/installers/${itemId}/availability`;
      } else if (routeConfig.type === 'contractors') {
        endpoint = `/contractors/${itemId}/availability`;
      }

      await api.put(endpoint, {
        status: newStatus
      });
      
      setTickets(prev => 
        prev.map(item => 
          item.id === itemId 
            ? { ...item, status: newStatus as any, availability_status: newStatus as any }
            : item
        )
      );
    } catch (error) {
      console.error(`Failed to update ${routeConfig.type} status:`, error);
    }
  };

  const filteredTickets = statusFilter === 'all' 
    ? tickets 
    : tickets.filter(item => {
        if (routeConfig.type === 'installers' || routeConfig.type === 'contractors') {
          return item.availability_status === statusFilter;
        }
        return item.status === statusFilter;
      });

  const getColumns = (): GridColDef[] => {
    const baseColumns: GridColDef[] = [
      { 
        field: 'id', 
        headerName: routeConfig.type === 'tickets' ? 'Ticket #' : 
                   routeConfig.type === 'service-orders' ? 'Order #' : 'ID', 
        width: 100 
      }
    ];

    if (routeConfig.type === 'tickets') {
      return [
        ...baseColumns,
        { field: 'title', headerName: 'Title', width: 250 },
        {
          field: 'customer',
          headerName: 'Customer',
          width: 200,
          valueGetter: (params) => params.row.customer?.name || 'N/A'
        },
        {
          field: 'priority',
          headerName: 'Priority',
          width: 120,
          renderCell: (params) => (
            <Chip
              label={params.value}
              color={
                params.value === 'urgent' ? 'error' :
                params.value === 'high' ? 'warning' :
                params.value === 'medium' ? 'info' : 'default'
              }
              size="small"
            />
          )
        },
        {
          field: 'status',
          headerName: 'Status',
          width: 150,
          renderCell: (params) => (
            <Chip
              label={params.value}
              color={
                params.value === 'resolved' ? 'success' :
                params.value === 'in_progress' ? 'warning' :
                params.value === 'open' ? 'error' : 'default'
              }
              size="small"
            />
          )
        },
        {
          field: 'created_at',
          headerName: 'Created',
          width: 150,
          valueFormatter: (params) => new Date(params.value).toLocaleDateString()
        },
        {
          field: 'actions',
          headerName: 'Actions',
          width: 200,
          renderCell: (params) => (
            <Box>
              {params.row.status === 'open' && (
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  onClick={() => handleStatusUpdate(params.row.id, 'in_progress')}
                  sx={{ mr: 1 }}
                >
                  Start
                </Button>
              )}
              {params.row.status === 'in_progress' && (
                <Button
                  size="small"
                  variant="outlined"
                  color="success"
                  onClick={() => handleStatusUpdate(params.row.id, 'resolved')}
                  sx={{ mr: 1 }}
                >
                  Resolve
                </Button>
              )}
              <Button size="small" variant="outlined">
                View
              </Button>
            </Box>
          )
        }
      ];
    } else if (routeConfig.type === 'service-orders') {
      return [
        ...baseColumns,
        { field: 'service_type', headerName: 'Service Type', width: 180 },
        {
          field: 'customer',
          headerName: 'Customer',
          width: 200,
          valueGetter: (params) => params.row.customer?.name || 'N/A'
        },
        { field: 'address', headerName: 'Service Address', width: 250 },
        {
          field: 'scheduled_date',
          headerName: 'Scheduled',
          width: 150,
          valueFormatter: (params) => params.value ? new Date(params.value).toLocaleDateString() : 'TBD'
        },
        {
          field: 'status',
          headerName: 'Status',
          width: 150,
          renderCell: (params) => (
            <Chip
              label={params.value}
              color={
                params.value === 'completed' ? 'success' :
                params.value === 'in_progress' ? 'warning' :
                params.value === 'scheduled' ? 'info' :
                params.value === 'pending' ? 'default' : 'error'
              }
              size="small"
            />
          )
        },
        {
          field: 'actions',
          headerName: 'Actions',
          width: 200,
          renderCell: (params) => (
            <Box>
              <Button size="small" variant="outlined" sx={{ mr: 1 }}>
                Schedule
              </Button>
              <Button size="small" variant="outlined">
                View
              </Button>
            </Box>
          )
        }
      ];
    } else if (routeConfig.type === 'installers' || routeConfig.type === 'contractors') {
      return [
        ...baseColumns,
        { field: 'name', headerName: 'Name', width: 200 },
        { field: 'email', headerName: 'Email', width: 200 },
        { field: 'phone', headerName: 'Phone', width: 150 },
        { field: 'specialties', headerName: 'Specialties', width: 200 },
        {
          field: 'availability_status',
          headerName: 'Status',
          width: 150,
          renderCell: (params) => (
            <Chip
              label={params.value || 'Available'}
              color={
                params.value === 'available' ? 'success' :
                params.value === 'busy' ? 'warning' :
                params.value === 'unavailable' ? 'error' : 'default'
              }
              size="small"
            />
          )
        },
        {
          field: 'actions',
          headerName: 'Actions',
          width: 200,
          renderCell: (params) => (
            <Box>
              <Button size="small" variant="outlined" sx={{ mr: 1 }}>
                Schedule
              </Button>
              <Button size="small" variant="outlined">
                Profile
              </Button>
            </Box>
          )
        }
      ];
    }

    return baseColumns;
  };

  const columns = getColumns();

  const getFilterOptions = () => {
    if (routeConfig.type === 'tickets') {
      return [
        { value: 'all', label: 'All Statuses' },
        { value: 'open', label: 'Open' },
        { value: 'in_progress', label: 'In Progress' },
        { value: 'resolved', label: 'Resolved' },
        { value: 'closed', label: 'Closed' }
      ];
    } else if (routeConfig.type === 'service-orders') {
      return [
        { value: 'all', label: 'All Statuses' },
        { value: 'pending', label: 'Pending' },
        { value: 'scheduled', label: 'Scheduled' },
        { value: 'in_progress', label: 'In Progress' },
        { value: 'completed', label: 'Completed' },
        { value: 'cancelled', label: 'Cancelled' }
      ];
    } else if (routeConfig.type === 'installers' || routeConfig.type === 'contractors') {
      return [
        { value: 'all', label: 'All Statuses' },
        { value: 'available', label: 'Available' },
        { value: 'busy', label: 'Busy' },
        { value: 'unavailable', label: 'Unavailable' }
      ];
    }
    return [{ value: 'all', label: 'All' }];
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box display="flex" alignItems="center" gap={1}>
          {routeConfig.icon}
          <Typography variant="h4">{routeConfig.title}</Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />}>
          {routeConfig.buttonText}
        </Button>
      </Box>

      <Box display="flex" gap={2} mb={3}>
        <FormControl sx={{ minWidth: 200 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={statusFilter}
            label="Status"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {getFilterOptions().map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={filteredTickets}
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

export default Tickets;