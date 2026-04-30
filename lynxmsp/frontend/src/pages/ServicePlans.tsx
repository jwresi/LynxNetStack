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
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  Alert,
  InputAdornment,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tooltip,
  Divider
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Refresh,
  Speed,
  AttachMoney,
  Wifi,
  Cable,
  Satellite,
  Router as RouterIcon,
  ExpandMore,
  Visibility,
  People,
  TrendingUp,
  Security,
  Cloud,
  Info
} from '@mui/icons-material';
import api from '../services/api';

interface ServicePlan {
  id: number;
  name: string;
  description: string;
  download_speed: number;
  upload_speed: number;
  monthly_price: number;
  setup_fee: number;
  data_cap?: number | null;
  service_type: string;
  technology: string;
  burst_speed_down?: number | null;
  burst_speed_up?: number | null;
  priority_level: number;
  billing_cycle: string;
  contract_length: number;
  early_termination_fee: number;
  static_ips_included: number;
  ipv6_enabled: boolean;
  cgnat_enabled: boolean;
  prorate_first_month: boolean;
  auto_renewal: boolean;
  available_in_areas: string[];
  status: string;
  equipment_included: string[];
  created_at?: string;
}

const ServicePlans: React.FC = () => {
  const [plans, setPlans] = useState<ServicePlan[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<ServicePlan | null>(null);
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<ServicePlan | null>(null);
  const [planToDelete, setPlanToDelete] = useState<ServicePlan | null>(null);

  const [newPlan, setNewPlan] = useState<Partial<ServicePlan>>({
    name: '',
    description: '',
    download_speed: 100,
    upload_speed: 20,
    monthly_price: 69.99,
    setup_fee: 0,
    data_cap: null,
    service_type: 'residential',
    technology: 'fiber',
    burst_speed_down: null,
    burst_speed_up: null,
    priority_level: 5,
    billing_cycle: 'monthly',
    prorate_first_month: true,
    auto_renewal: true,
    contract_length: 12,
    early_termination_fee: 0,
    static_ips_included: 0,
    ipv6_enabled: true,
    cgnat_enabled: false,
    equipment_included: [],
    status: 'active',
    available_in_areas: []
  });

  useEffect(() => {
    fetchServicePlans();
  }, []);

  const fetchServicePlans = async () => {
    try {
      const response = await api.get('/service-plans');
      setPlans(response.data);
    } catch (error) {
      console.error('Failed to fetch service plans:', error);
      // For now, set empty array if API fails
      setPlans([]);
    }
  };

  const handleCreatePlan = async () => {
    setLoading(true);
    try {
      if (editingPlan) {
        // Update existing plan
        await api.put(`/service-plans/${editingPlan.id}`, newPlan);
      } else {
        // Create new plan
        await api.post('/service-plans', newPlan);
      }
      
      // Reset form
      setNewPlan({
        name: '',
        description: '',
        download_speed: 100,
        upload_speed: 20,
        monthly_price: 69.99,
        setup_fee: 0,
        data_cap: null,
        service_type: 'residential',
        technology: 'fiber',
        burst_speed_down: null,
        burst_speed_up: null,
        priority_level: 5,
        billing_cycle: 'monthly',
        prorate_first_month: true,
        auto_renewal: true,
        contract_length: 12,
        early_termination_fee: 0,
        static_ips_included: 0,
        ipv6_enabled: true,
        cgnat_enabled: false,
        equipment_included: [],
        status: 'active',
        available_in_areas: []
      });
      setDialogOpen(false);
      setEditingPlan(null);
      fetchServicePlans();
    } catch (error) {
      console.error('Failed to save service plan:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEditPlan = (plan: ServicePlan) => {
    setEditingPlan(plan);
    setNewPlan(plan);
    setDialogOpen(true);
  };

  const handleDeletePlan = (plan: ServicePlan) => {
    setPlanToDelete(plan);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!planToDelete) return;
    
    setDeleteLoading(true);
    try {
      await api.delete(`/service-plans/${planToDelete.id}`);
      fetchServicePlans();
      setDeleteDialogOpen(false);
      setPlanToDelete(null);
    } catch (error) {
      console.error('Failed to delete service plan:', error);
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCancelDelete = () => {
    setDeleteDialogOpen(false);
    setPlanToDelete(null);
  };

  const handleViewDetails = (plan: ServicePlan) => {
    setSelectedPlan(plan);
    setDetailsDialogOpen(true);
  };

  const handleCloseDetails = () => {
    setDetailsDialogOpen(false);
    setSelectedPlan(null);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'success';
      case 'inactive':
        return 'default';
      case 'deprecated':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getTechnologyIcon = (technology: string) => {
    switch (technology) {
      case 'fiber':
        return <Cable color="primary" />;
      case 'wireless':
        return <Wifi color="info" />;
      case 'satellite':
        return <Satellite color="secondary" />;
      case 'cable':
        return <RouterIcon color="action" />;
      default:
        return <Cable />;
    }
  };

  const formatSpeed = (speed: number) => {
    if (speed >= 1000) {
      return `${speed / 1000} Gbps`;
    }
    return `${speed} Mbps`;
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Speed />
          Service Plans Management
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchServicePlans}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setDialogOpen(true)}
          >
            Create Plan
          </Button>
        </Box>
      </Box>

      <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <Tab label="All Plans" />
        <Tab label="Residential" />
        <Tab label="Business" />
        <Tab label="Enterprise" />
      </Tabs>

      {/* Service Plans Grid */}
      <Grid container spacing={3}>
        {plans
          .filter(plan => tabValue === 0 || 
            (tabValue === 1 && plan.service_type === 'residential') ||
            (tabValue === 2 && plan.service_type === 'business') ||
            (tabValue === 3 && plan.service_type === 'enterprise'))
          .map((plan) => (
          <Grid item xs={12} md={6} lg={4} key={plan.id}>
            <Card sx={{ 
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              position: 'relative',
              '&:hover': {
                boxShadow: 4,
                transform: 'translateY(-2px)',
                transition: 'all 0.2s ease-in-out'
              }
            }}>
              {plan.service_type === 'enterprise' && (
                <Chip 
                  label="Most Popular" 
                  color="primary" 
                  size="small"
                  sx={{ 
                    position: 'absolute', 
                    top: 16, 
                    right: 16,
                    zIndex: 1
                  }}
                />
              )}
              
              <CardContent sx={{ flex: 1 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {getTechnologyIcon(plan.technology)}
                    <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                      {plan.name}
                    </Typography>
                  </Box>
                  <Chip 
                    label={plan.status} 
                    color={getStatusColor(plan.status)}
                    size="small"
                  />
                </Box>

                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  {plan.description}
                </Typography>

                {/* Speed Information */}
                <Box sx={{ 
                  p: 2, 
                  bgcolor: 'grey.50', 
                  borderRadius: 2, 
                  mb: 2,
                  border: '1px solid',
                  borderColor: 'grey.200'
                }}>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">Download</Typography>
                      <Typography variant="h6" color="primary">
                        {formatSpeed(plan.download_speed)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">Upload</Typography>
                      <Typography variant="h6" color="secondary">
                        {formatSpeed(plan.upload_speed)}
                      </Typography>
                    </Grid>
                  </Grid>
                </Box>

                {/* Pricing */}
                <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: 2 }}>
                  <Typography variant="h4" color="primary" sx={{ fontWeight: 'bold' }}>
                    ${plan.monthly_price}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    /month
                  </Typography>
                  {plan.setup_fee > 0 && (
                    <Chip 
                      label={`$${plan.setup_fee} setup`}
                      size="small"
                      variant="outlined"
                      color="warning"
                    />
                  )}
                </Box>

                {/* Features */}
                <Box sx={{ mb: 2 }}>
                  <Grid container spacing={1}>
                    <Grid item xs={12}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <People fontSize="small" color="action" />
                        <Typography variant="body2">
                          {plan.service_type} • {plan.technology}
                        </Typography>
                      </Box>
                    </Grid>
                    
                    {plan.data_cap && (
                      <Grid item xs={12}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Cloud fontSize="small" color="action" />
                          <Typography variant="body2">
                            {plan.data_cap}GB data cap
                          </Typography>
                        </Box>
                      </Grid>
                    )}

                    {plan.static_ips_included > 0 && (
                      <Grid item xs={12}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Security fontSize="small" color="action" />
                          <Typography variant="body2">
                            {plan.static_ips_included} static IP{plan.static_ips_included > 1 ? 's' : ''}
                          </Typography>
                        </Box>
                      </Grid>
                    )}

                    <Grid item xs={12}>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        {plan.ipv6_enabled && (
                          <Chip label="IPv6" size="small" variant="outlined" color="info" />
                        )}
                        {plan.cgnat_enabled && (
                          <Chip label="CGNAT" size="small" variant="outlined" color="warning" />
                        )}
                        <Chip 
                          label={`${plan.contract_length}mo contract`} 
                          size="small" 
                          variant="outlined" 
                        />
                      </Box>
                    </Grid>
                  </Grid>
                </Box>

                {/* Priority Level */}
                <Box sx={{ mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <TrendingUp fontSize="small" color="action" />
                    <Typography variant="body2">
                      Priority Level: {plan.priority_level}/10
                    </Typography>
                  </Box>
                  <Box sx={{ 
                    height: 4, 
                    bgcolor: 'grey.200', 
                    borderRadius: 2,
                    overflow: 'hidden'
                  }}>
                    <Box sx={{ 
                      height: '100%', 
                      width: `${plan.priority_level * 10}%`,
                      bgcolor: plan.priority_level >= 8 ? 'success.main' : 
                               plan.priority_level >= 5 ? 'warning.main' : 'error.main'
                    }} />
                  </Box>
                </Box>
              </CardContent>

              {/* Action Buttons */}
              <Box sx={{ p: 2, pt: 0 }}>
                <Grid container spacing={1}>
                  <Grid item xs={4}>
                    <Tooltip title="View Details">
                      <IconButton 
                        size="small" 
                        color="info"
                        onClick={() => handleViewDetails(plan)}
                      >
                        <Visibility />
                      </IconButton>
                    </Tooltip>
                  </Grid>
                  <Grid item xs={4}>
                    <Tooltip title="Edit Plan">
                      <IconButton 
                        size="small" 
                        color="primary"
                        onClick={() => handleEditPlan(plan)}
                      >
                        <Edit />
                      </IconButton>
                    </Tooltip>
                  </Grid>
                  <Grid item xs={4}>
                    <Tooltip title="Delete Plan">
                      <IconButton 
                        size="small" 
                        color="error"
                        onClick={() => handleDeletePlan(plan)}
                      >
                        <Delete />
                      </IconButton>
                    </Tooltip>
                  </Grid>
                </Grid>
              </Box>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Create/Edit Plan Dialog */}
      <Dialog 
        open={dialogOpen} 
        onClose={() => {
          setDialogOpen(false);
          setEditingPlan(null);
        }} 
        maxWidth="md" 
        fullWidth
      >
        <DialogTitle>
          {editingPlan ? 'Edit Service Plan' : 'Create New Service Plan'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Basic Information</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Plan Name"
                      value={newPlan.name}
                      onChange={(e) => setNewPlan({...newPlan, name: e.target.value})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <FormControl fullWidth margin="normal">
                      <InputLabel>Service Type</InputLabel>
                      <Select
                        value={newPlan.service_type}
                        onChange={(e) => setNewPlan({...newPlan, service_type: e.target.value})}
                        label="Service Type"
                      >
                        <MenuItem value="residential">Residential</MenuItem>
                        <MenuItem value="business">Business</MenuItem>
                        <MenuItem value="enterprise">Enterprise</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="Description"
                      multiline
                      rows={3}
                      value={newPlan.description}
                      onChange={(e) => setNewPlan({...newPlan, description: e.target.value})}
                      margin="normal"
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Speed & Technology</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Download Speed (Mbps)"
                      type="number"
                      value={newPlan.download_speed}
                      onChange={(e) => setNewPlan({...newPlan, download_speed: parseInt(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Upload Speed (Mbps)"
                      type="number"
                      value={newPlan.upload_speed}
                      onChange={(e) => setNewPlan({...newPlan, upload_speed: parseInt(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <FormControl fullWidth margin="normal">
                      <InputLabel>Technology</InputLabel>
                      <Select
                        value={newPlan.technology}
                        onChange={(e) => setNewPlan({...newPlan, technology: e.target.value})}
                        label="Technology"
                      >
                        <MenuItem value="fiber">Fiber</MenuItem>
                        <MenuItem value="wireless">Wireless</MenuItem>
                        <MenuItem value="cable">Cable</MenuItem>
                        <MenuItem value="dsl">DSL</MenuItem>
                        <MenuItem value="satellite">Satellite</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Priority Level (1-10)"
                      type="number"
                      inputProps={{ min: 1, max: 10 }}
                      value={newPlan.priority_level}
                      onChange={(e) => setNewPlan({...newPlan, priority_level: parseInt(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Pricing & Billing</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Monthly Price"
                      type="number"
                      InputProps={{
                        startAdornment: <InputAdornment position="start">$</InputAdornment>,
                      }}
                      value={newPlan.monthly_price}
                      onChange={(e) => setNewPlan({...newPlan, monthly_price: parseFloat(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Setup Fee"
                      type="number"
                      InputProps={{
                        startAdornment: <InputAdornment position="start">$</InputAdornment>,
                      }}
                      value={newPlan.setup_fee}
                      onChange={(e) => setNewPlan({...newPlan, setup_fee: parseFloat(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <FormControl fullWidth margin="normal">
                      <InputLabel>Billing Cycle</InputLabel>
                      <Select
                        value={newPlan.billing_cycle}
                        onChange={(e) => setNewPlan({...newPlan, billing_cycle: e.target.value})}
                        label="Billing Cycle"
                      >
                        <MenuItem value="monthly">Monthly</MenuItem>
                        <MenuItem value="quarterly">Quarterly</MenuItem>
                        <MenuItem value="annually">Annually</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Contract Length (months)"
                      type="number"
                      value={newPlan.contract_length}
                      onChange={(e) => setNewPlan({...newPlan, contract_length: parseInt(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Advanced Features</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Static IPs Included"
                      type="number"
                      value={newPlan.static_ips_included}
                      onChange={(e) => setNewPlan({...newPlan, static_ips_included: parseInt(e.target.value)})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Data Cap (GB)"
                      type="number"
                      placeholder="Leave empty for unlimited"
                      value={newPlan.data_cap || ''}
                      onChange={(e) => setNewPlan({...newPlan, data_cap: e.target.value ? parseInt(e.target.value) : null})}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={newPlan.ipv6_enabled}
                          onChange={(e) => setNewPlan({...newPlan, ipv6_enabled: e.target.checked})}
                        />
                      }
                      label="IPv6 Enabled"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={newPlan.cgnat_enabled}
                          onChange={(e) => setNewPlan({...newPlan, cgnat_enabled: e.target.checked})}
                        />
                      }
                      label="CGNAT Enabled"
                    />
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setDialogOpen(false);
            setEditingPlan(null);
          }}>
            Cancel
          </Button>
          <Button 
            onClick={handleCreatePlan} 
            variant="contained"
            disabled={loading || !newPlan.name || !newPlan.monthly_price}
          >
            {editingPlan ? 'Update Plan' : 'Create Plan'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Service Plan Details Dialog */}
      <Dialog open={detailsDialogOpen} onClose={handleCloseDetails} maxWidth="md" fullWidth>
        <DialogTitle>
          Service Plan Details: {selectedPlan?.name}
        </DialogTitle>
        <DialogContent>
          {selectedPlan && (
            <Box>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Basic Information</Typography>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Name</Typography>
                    <Typography variant="body1">{selectedPlan.name}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Description</Typography>
                    <Typography variant="body1">{selectedPlan.description}</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Service Type</Typography>
                    <Typography variant="body1" sx={{ textTransform: 'capitalize' }}>
                      {selectedPlan.service_type}
                    </Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Technology</Typography>
                    <Typography variant="body1" sx={{ textTransform: 'capitalize' }}>
                      {selectedPlan.technology}
                    </Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Status</Typography>
                    <Chip
                      label={selectedPlan.status}
                      color={
                        selectedPlan.status === 'active' ? 'success' :
                        selectedPlan.status === 'inactive' ? 'default' : 'warning'
                      }
                      size="small"
                    />
                  </Box>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Speed & Pricing</Typography>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Download Speed</Typography>
                    <Typography variant="body1">{selectedPlan.download_speed} Mbps</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Upload Speed</Typography>
                    <Typography variant="body1">{selectedPlan.upload_speed} Mbps</Typography>
                  </Box>
                  {selectedPlan.burst_speed_down && (
                    <Box mb={2}>
                      <Typography variant="body2" color="text.secondary">Burst Speed (Down/Up)</Typography>
                      <Typography variant="body1">
                        {selectedPlan.burst_speed_down}/{selectedPlan.burst_speed_up} Mbps
                      </Typography>
                    </Box>
                  )}
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Monthly Price</Typography>
                    <Typography variant="body1">${selectedPlan.monthly_price}/month</Typography>
                  </Box>
                  <Box mb={2}>
                    <Typography variant="body2" color="text.secondary">Setup Fee</Typography>
                    <Typography variant="body1">${selectedPlan.setup_fee}</Typography>
                  </Box>
                  {selectedPlan.data_cap && (
                    <Box mb={2}>
                      <Typography variant="body2" color="text.secondary">Data Cap</Typography>
                      <Typography variant="body1">{selectedPlan.data_cap} GB</Typography>
                    </Box>
                  )}
                </Grid>

                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="h6" gutterBottom>Contract & Billing</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6} md={3}>
                      <Typography variant="body2" color="text.secondary">Billing Cycle</Typography>
                      <Typography variant="body1" sx={{ textTransform: 'capitalize' }}>
                        {selectedPlan.billing_cycle}
                      </Typography>
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <Typography variant="body2" color="text.secondary">Contract Length</Typography>
                      <Typography variant="body1">{selectedPlan.contract_length} months</Typography>
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <Typography variant="body2" color="text.secondary">Early Termination Fee</Typography>
                      <Typography variant="body1">${selectedPlan.early_termination_fee}</Typography>
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <Typography variant="body2" color="text.secondary">Priority Level</Typography>
                      <Typography variant="body1">{selectedPlan.priority_level}</Typography>
                    </Grid>
                  </Grid>
                </Grid>

                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="h6" gutterBottom>Features</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6} md={4}>
                      <Typography variant="body2" color="text.secondary">Static IPs Included</Typography>
                      <Typography variant="body1">{selectedPlan.static_ips_included}</Typography>
                    </Grid>
                    <Grid item xs={6} md={4}>
                      <Typography variant="body2" color="text.secondary">IPv6 Support</Typography>
                      <Chip
                        label={selectedPlan.ipv6_enabled ? 'Enabled' : 'Disabled'}
                        color={selectedPlan.ipv6_enabled ? 'success' : 'default'}
                        size="small"
                      />
                    </Grid>
                    <Grid item xs={6} md={4}>
                      <Typography variant="body2" color="text.secondary">CGNAT</Typography>
                      <Chip
                        label={selectedPlan.cgnat_enabled ? 'Enabled' : 'Disabled'}
                        color={selectedPlan.cgnat_enabled ? 'warning' : 'success'}
                        size="small"
                      />
                    </Grid>
                    <Grid item xs={6} md={4}>
                      <Typography variant="body2" color="text.secondary">Prorate First Month</Typography>
                      <Chip
                        label={selectedPlan.prorate_first_month ? 'Yes' : 'No'}
                        color={selectedPlan.prorate_first_month ? 'success' : 'default'}
                        size="small"
                      />
                    </Grid>
                    <Grid item xs={6} md={4}>
                      <Typography variant="body2" color="text.secondary">Auto Renewal</Typography>
                      <Chip
                        label={selectedPlan.auto_renewal ? 'Enabled' : 'Disabled'}
                        color={selectedPlan.auto_renewal ? 'success' : 'default'}
                        size="small"
                      />
                    </Grid>
                  </Grid>
                </Grid>

                {selectedPlan.equipment_included && selectedPlan.equipment_included.length > 0 && (
                  <Grid item xs={12}>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="h6" gutterBottom>Equipment Included</Typography>
                    <Box>
                      {selectedPlan.equipment_included.map((equipment, index) => (
                        <Chip
                          key={index}
                          label={equipment}
                          variant="outlined"
                          sx={{ mr: 1, mb: 1 }}
                        />
                      ))}
                    </Box>
                  </Grid>
                )}

                {selectedPlan.available_in_areas && selectedPlan.available_in_areas.length > 0 && (
                  <Grid item xs={12}>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="h6" gutterBottom>Available Areas</Typography>
                    <Box>
                      {selectedPlan.available_in_areas.map((area, index) => (
                        <Chip
                          key={index}
                          label={area}
                          color="primary"
                          variant="outlined"
                          sx={{ mr: 1, mb: 1 }}
                        />
                      ))}
                    </Box>
                  </Grid>
                )}
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDetails}>Close</Button>
          {selectedPlan && (
            <Button 
              onClick={() => {
                handleCloseDetails();
                handleEditPlan(selectedPlan);
              }}
              variant="contained"
              startIcon={<Edit />}
            >
              Edit Plan
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={handleCancelDelete} maxWidth="sm" fullWidth>
        <DialogTitle>Delete Service Plan</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. Customers using this plan may be affected.
          </Alert>
          <Typography>
            Are you sure you want to delete the service plan <strong>{planToDelete?.name}</strong>?
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
            {deleteLoading ? 'Deleting...' : 'Delete Plan'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ServicePlans;