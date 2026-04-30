import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Chip,
  Button,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert
} from '@mui/material';
import { Edit, Receipt, Support, Delete } from '@mui/icons-material';
import api from '../services/api';
import { Customer, Invoice, Ticket } from '../types';

function CustomerDetail() {
  const { id } = useParams<{ id: string }>();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    status: 'active' as 'active' | 'suspended' | 'inactive'
  });

  useEffect(() => {
    const fetchCustomerData = async () => {
      if (!id) return;

      try {
        const [customerRes, invoicesRes, ticketsRes] = await Promise.all([
          api.get(`/customers/${id}`),
          api.get(`/invoices?customer_id=${id}`),
          api.get(`/tickets?customer_id=${id}`)
        ]);

        setCustomer(customerRes.data);
        setInvoices(invoicesRes.data);
        setTickets(ticketsRes.data);
        
        // Initialize edit form with customer data
        setEditForm({
          name: customerRes.data.name || '',
          email: customerRes.data.email || '',
          phone: customerRes.data.phone || '',
          address: customerRes.data.address || '',
          status: customerRes.data.status || 'active'
        });
      } catch (error) {
        console.error('Failed to fetch customer data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchCustomerData();
  }, [id]);

  const handleEditCustomer = () => {
    setEditDialogOpen(true);
  };

  const handleSaveCustomer = async () => {
    try {
      await api.put(`/customers/${id}`, editForm);
      
      // Update local state with new data
      setCustomer(prev => prev ? { ...prev, ...editForm } : null);
      setEditDialogOpen(false);
    } catch (error) {
      console.error('Failed to update customer:', error);
      alert('Failed to update customer. Please try again.');
    }
  };

  const handleCancelEdit = () => {
    // Reset form to original customer data
    if (customer) {
      setEditForm({
        name: customer.name || '',
        email: customer.email || '',
        phone: customer.phone || '',
        address: customer.address || '',
        status: customer.status || 'active'
      });
    }
    setEditDialogOpen(false);
  };

  const handleDeleteCustomer = () => {
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!customer) return;
    
    setDeleteLoading(true);
    try {
      await api.delete(`/customers/${customer.id}`);
      // Navigate back to customers list after successful deletion
      window.location.href = '/customers';
    } catch (error) {
      console.error('Failed to delete customer:', error);
      alert('Failed to delete customer. Please try again.');
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCancelDelete = () => {
    setDeleteDialogOpen(false);
  };

  if (loading) {
    return <Typography>Loading...</Typography>;
  }

  if (!customer) {
    return <Typography>Customer not found</Typography>;
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">{customer.name}</Typography>
        <Box display="flex" gap={2}>
          <Button 
            variant="contained" 
            startIcon={<Edit />}
            onClick={handleEditCustomer}
          >
            Edit Customer
          </Button>
          <Button 
            variant="outlined" 
            color="error"
            startIcon={<Delete />}
            onClick={handleDeleteCustomer}
          >
            Delete Customer
          </Button>
        </Box>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Customer Information
            </Typography>
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary">Email</Typography>
              <Typography>{customer.email}</Typography>
            </Box>
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary">Phone</Typography>
              <Typography>{customer.phone || 'N/A'}</Typography>
            </Box>
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary">Address</Typography>
              <Typography>{customer.address || 'N/A'}</Typography>
            </Box>
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary">Status</Typography>
              <Chip
                label={customer.status}
                color={
                  customer.status === 'active' ? 'success' :
                  customer.status === 'suspended' ? 'warning' : 'default'
                }
                size="small"
              />
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Service Plan
            </Typography>
            {customer.service_plan && (
              <Box>
                <Typography variant="h6">{customer.service_plan.name}</Typography>
                <Typography>
                  Speed: {customer.service_plan.speed_down}/{customer.service_plan.speed_up} Mbps
                </Typography>
                <Typography>
                  Price: ${customer.service_plan.price}/month
                </Typography>
              </Box>
            )}
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">Recent Invoices</Typography>
              <Button startIcon={<Receipt />} size="small">
                View All
              </Button>
            </Box>
            <Divider sx={{ mb: 2 }} />
            {invoices.slice(0, 3).map((invoice) => (
              <Box key={invoice.id} mb={1}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">
                    Invoice #{invoice.id}
                  </Typography>
                  <Typography variant="body2">
                    ${invoice.amount}
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="caption" color="text.secondary">
                    Due: {new Date(invoice.due_date).toLocaleDateString()}
                  </Typography>
                  <Chip
                    label={invoice.payment_status}
                    size="small"
                    color={
                      invoice.payment_status === 'paid' ? 'success' :
                      invoice.payment_status === 'overdue' ? 'error' : 'warning'
                    }
                  />
                </Box>
              </Box>
            ))}
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">Support Tickets</Typography>
              <Button startIcon={<Support />} size="small">
                View All
              </Button>
            </Box>
            <Divider sx={{ mb: 2 }} />
            {tickets.slice(0, 3).map((ticket) => (
              <Box key={ticket.id} mb={1}>
                <Typography variant="body2">
                  {ticket.title}
                </Typography>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="caption" color="text.secondary">
                    {new Date(ticket.created_at).toLocaleDateString()}
                  </Typography>
                  <Chip
                    label={ticket.status}
                    size="small"
                    color={
                      ticket.status === 'resolved' ? 'success' :
                      ticket.status === 'open' ? 'error' : 'warning'
                    }
                  />
                </Box>
              </Box>
            ))}
          </Paper>
        </Grid>
      </Grid>

      {/* Edit Customer Dialog */}
      <Dialog open={editDialogOpen} onClose={handleCancelEdit} maxWidth="sm" fullWidth>
        <DialogTitle>Edit Customer</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1 }}>
            <TextField
              fullWidth
              label="Name"
              value={editForm.name}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              margin="normal"
              required
            />
            <TextField
              fullWidth
              label="Email"
              type="email"
              value={editForm.email}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
              margin="normal"
              required
            />
            <TextField
              fullWidth
              label="Phone"
              value={editForm.phone}
              onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
              margin="normal"
            />
            <TextField
              fullWidth
              label="Address"
              value={editForm.address}
              onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
              margin="normal"
              multiline
              rows={2}
            />
            <TextField
              fullWidth
              select
              label="Status"
              value={editForm.status}
              onChange={(e) => setEditForm({ ...editForm, status: e.target.value as 'active' | 'suspended' | 'inactive' })}
              margin="normal"
              SelectProps={{
                native: true,
              }}
            >
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="inactive">Inactive</option>
            </TextField>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelEdit}>Cancel</Button>
          <Button onClick={handleSaveCustomer} variant="contained">
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Customer Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleCancelDelete} maxWidth="sm" fullWidth>
        <DialogTitle>Delete Customer</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. All customer data, invoices, and tickets will be permanently deleted.
          </Alert>
          <Typography>
            Are you sure you want to delete customer <strong>{customer?.name}</strong>?
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
            {deleteLoading ? 'Deleting...' : 'Delete Customer'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default CustomerDetail;