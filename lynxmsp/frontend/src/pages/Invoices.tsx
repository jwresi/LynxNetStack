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
  InputLabel,
  Card,
  CardContent,
  Grid
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { 
  Add, 
  Receipt, 
  Payment, 
  CreditCard, 
  Analytics,
  TrendingUp,
  AccountBalance,
  PaymentOutlined
} from '@mui/icons-material';
import api from '../services/api';
import { Invoice } from '../types';

function Invoices() {
  const location = useLocation();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');

  // Determine current section based on route
  const getCurrentSection = () => {
    if (location.pathname === '/payments') return 'payments';
    if (location.pathname === '/payment-methods') return 'payment-methods';
    if (location.pathname === '/billing-reports') return 'billing-reports';
    return 'invoices';
  };

  const currentSection = getCurrentSection();

  // Get section-specific configuration
  const getSectionConfig = () => {
    switch (currentSection) {
      case 'payments':
        return {
          title: 'Payments',
          icon: <Payment />,
          description: 'Payment history and processing',
          buttonText: 'Record Payment',
          buttonIcon: <PaymentOutlined />
        };
      case 'payment-methods':
        return {
          title: 'Payment Methods',
          icon: <CreditCard />,
          description: 'Customer payment methods management',
          buttonText: 'Add Payment Method',
          buttonIcon: <Add />
        };
      case 'billing-reports':
        return {
          title: 'Billing Reports',
          icon: <Analytics />,
          description: 'Revenue and billing analytics',
          buttonText: 'Generate Report',
          buttonIcon: <TrendingUp />
        };
      default:
        return {
          title: 'Invoices',
          icon: <Receipt />,
          description: 'Invoice management and tracking',
          buttonText: 'Generate Invoice',
          buttonIcon: <Add />
        };
    }
  };

  const sectionConfig = getSectionConfig();

  useEffect(() => {
    const fetchInvoices = async () => {
      try {
        const response = await api.get('/invoices');
        setInvoices(response.data);
      } catch (error) {
        console.error('Failed to fetch invoices:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchInvoices();
  }, []);

  const handleStatusUpdate = async (invoiceId: number, newStatus: string) => {
    try {
      await api.put(`/invoices/${invoiceId}/payment-status`, {
        payment_status: newStatus
      });
      
      setInvoices(prev => 
        prev.map(invoice => 
          invoice.id === invoiceId 
            ? { ...invoice, payment_status: newStatus as any }
            : invoice
        )
      );
    } catch (error) {
      console.error('Failed to update invoice status:', error);
    }
  };

  const filteredInvoices = statusFilter === 'all' 
    ? invoices 
    : invoices.filter(invoice => invoice.payment_status === statusFilter);

  // Render different content based on section
  const renderPaymentsContent = () => (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>Payment Overview</Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h4" color="success.main">$12,340</Typography>
                <Typography variant="body2" color="text.secondary">Total Received This Month</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h4" color="warning.main">$5,670</Typography>
                <Typography variant="body2" color="text.secondary">Pending Payments</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h4" color="error.main">$2,890</Typography>
                <Typography variant="body2" color="text.secondary">Overdue Payments</Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Paper>
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={invoices.filter(invoice => invoice.payment_status === 'paid')}
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

  const renderPaymentMethodsContent = () => (
    <Box>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>Customer Payment Methods</Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          Manage and configure payment methods for your customers
        </Typography>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight={400}>
          <Box textAlign="center">
            <CreditCard sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary">Payment Methods Management</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Configure credit cards, bank accounts, and other payment options
            </Typography>
            <Button variant="contained" startIcon={<Add />}>
              Add Payment Method
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );

  const renderBillingReportsContent = () => (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>Revenue Analytics</Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  <TrendingUp color="success" sx={{ mr: 1 }} />
                  <Typography variant="h6">Monthly Revenue</Typography>
                </Box>
                <Typography variant="h4" color="success.main">$18,010</Typography>
                <Typography variant="body2" color="text.secondary">+12% from last month</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  <AccountBalance color="primary" sx={{ mr: 1 }} />
                  <Typography variant="h6">Annual Revenue</Typography>
                </Box>
                <Typography variant="h4" color="primary.main">$216,120</Typography>
                <Typography variant="body2" color="text.secondary">YTD Performance</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  <Receipt color="info" sx={{ mr: 1 }} />
                  <Typography variant="h6">Total Invoices</Typography>
                </Box>
                <Typography variant="h4" color="info.main">{invoices.length}</Typography>
                <Typography variant="body2" color="text.secondary">This month</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  <Analytics color="warning" sx={{ mr: 1 }} />
                  <Typography variant="h6">Avg. Invoice</Typography>
                </Box>
                <Typography variant="h4" color="warning.main">$1,200</Typography>
                <Typography variant="body2" color="text.secondary">Per customer</Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Paper>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>Billing Reports</Typography>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
          <Box textAlign="center">
            <Analytics sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary">Advanced Reporting</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Generate detailed billing and revenue reports
            </Typography>
            <Button variant="contained" startIcon={<TrendingUp />}>
              Generate Report
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );

  const renderInvoicesContent = () => (
    <Box>
      <Box display="flex" gap={2} mb={3}>
        <FormControl sx={{ minWidth: 200 }}>
          <InputLabel>Payment Status</InputLabel>
          <Select
            value={statusFilter}
            label="Payment Status"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <MenuItem value="all">All Statuses</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="paid">Paid</MenuItem>
            <MenuItem value="overdue">Overdue</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={filteredInvoices}
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

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'Invoice #', width: 100 },
    {
      field: 'customer',
      headerName: 'Customer',
      width: 200,
      valueGetter: (params) => params.row.customer?.name || 'N/A'
    },
    {
      field: 'amount',
      headerName: 'Amount',
      width: 120,
      valueFormatter: (params) => `$${params.value}`
    },
    {
      field: 'due_date',
      headerName: 'Due Date',
      width: 150,
      valueFormatter: (params) => new Date(params.value).toLocaleDateString()
    },
    {
      field: 'payment_status',
      headerName: 'Status',
      width: 150,
      renderCell: (params) => (
        <Chip
          label={params.value}
          color={
            params.value === 'paid' ? 'success' :
            params.value === 'overdue' ? 'error' : 'warning'
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
          {params.row.payment_status === 'pending' && (
            <Button
              size="small"
              variant="outlined"
              color="success"
              onClick={() => handleStatusUpdate(params.row.id, 'paid')}
              sx={{ mr: 1 }}
            >
              Mark Paid
            </Button>
          )}
          <Button size="small" variant="outlined">
            View
          </Button>
        </Box>
      )
    }
  ];

  // Function to render content based on current section
  const renderContent = () => {
    switch (currentSection) {
      case 'payments':
        return renderPaymentsContent();
      case 'payment-methods':
        return renderPaymentMethodsContent();
      case 'billing-reports':
        return renderBillingReportsContent();
      default:
        return renderInvoicesContent();
    }
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box display="flex" alignItems="center" gap={2}>
          {sectionConfig.icon}
          <Box>
            <Typography variant="h4">{sectionConfig.title}</Typography>
            <Typography variant="body2" color="text.secondary">
              {sectionConfig.description}
            </Typography>
          </Box>
        </Box>
        <Button variant="contained" startIcon={sectionConfig.buttonIcon}>
          {sectionConfig.buttonText}
        </Button>
      </Box>

      {renderContent()}
    </Box>
  );
}

export default Invoices;