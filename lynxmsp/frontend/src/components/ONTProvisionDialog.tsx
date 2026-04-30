import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Typography,
  Box,
  Alert,
  Stepper,
  Step,
  StepLabel,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Switch,
  FormControlLabel,
  Divider
} from '@mui/material';
import {
  Cable,
  NetworkCheck,
  Wifi,
  Security,
  CheckCircle,
  Warning
} from '@mui/icons-material';
import { api } from '../services/api';

interface ONTProvisionDialogProps {
  open: boolean;
  onClose: () => void;
  oltDeviceId?: number;
  onSuccess: () => void;
}

interface Customer {
  id: number;
  name: string;
  email: string;
  address: string;
}

interface ServicePlan {
  id: number;
  name: string;
  download_speed: number;
  upload_speed: number;
  monthly_price: number;
}

const steps = ['Basic Info', 'Service Config', 'WiFi Setup', 'Review'];

const ONTProvisionDialog: React.FC<ONTProvisionDialogProps> = ({
  open,
  onClose,
  oltDeviceId,
  onSuccess
}) => {
  const [activeStep, setActiveStep] = useState(0);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [servicePlans, setServicePlans] = useState<ServicePlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Form data
  const [formData, setFormData] = useState({
    customer_id: '',
    pon_port: 'pon1',
    ont_id: 1,
    serial_number: '',
    service_profile: 'default',
    bandwidth_profile: 'residential',
    vlan_config: {
      management_vlan: 100,
      service_vlan: 200,
      internet_vlan: 300
    },
    wifi_config: {
      enabled: true,
      ssid: '',
      password: '',
      security: 'WPA2',
      channel_2g: 'auto',
      channel_5g: 'auto'
    },
    notes: ''
  });

  useEffect(() => {
    if (open) {
      loadCustomers();
      loadServicePlans();
    }
  }, [open]);

  const loadCustomers = async () => {
    try {
      const response = await api.get('/customers');
      setCustomers(response.data);
    } catch (err) {
      console.error('Error loading customers:', err);
    }
  };

  const loadServicePlans = async () => {
    try {
      const response = await api.get('/service-plans');
      setServicePlans(response.data);
    } catch (err) {
      console.error('Error loading service plans:', err);
    }
  };

  const handleNext = () => {
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
  };

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1);
  };

  const handleProvision = async () => {
    if (!oltDeviceId) {
      setError('OLT device not selected');
      return;
    }

    setLoading(true);
    setError('');

    try {
      await api.post(`/tplink/olt/${oltDeviceId}/provision-ont`, {
        olt_device_id: oltDeviceId,
        customer_id: parseInt(formData.customer_id),
        pon_port: formData.pon_port,
        ont_id: formData.ont_id,
        serial_number: formData.serial_number,
        service_profile: formData.service_profile,
        bandwidth_profile: formData.bandwidth_profile,
        vlan_config: formData.vlan_config,
        wifi_config: formData.wifi_config,
        notes: formData.notes
      });

      onSuccess();
      onClose();
      setActiveStep(0);
      setFormData({
        customer_id: '',
        pon_port: 'pon1',
        ont_id: 1,
        serial_number: '',
        service_profile: 'default',
        bandwidth_profile: 'residential',
        vlan_config: {
          management_vlan: 100,
          service_vlan: 200,
          internet_vlan: 300
        },
        wifi_config: {
          enabled: true,
          ssid: '',
          password: '',
          security: 'WPA2',
          channel_2g: 'auto',
          channel_5g: 'auto'
        },
        notes: ''
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to provision ONT');
    } finally {
      setLoading(false);
    }
  };

  const generateWiFiCredentials = () => {
    const customer = customers.find(c => c.id === parseInt(formData.customer_id));
    if (customer) {
      const ssid = `${customer.name.replace(/\s+/g, '')}_WiFi`;
      const password = Math.random().toString(36).slice(-8) + Math.random().toString(36).slice(-8).toUpperCase();
      
      setFormData({
        ...formData,
        wifi_config: {
          ...formData.wifi_config,
          ssid,
          password
        }
      });
    }
  };

  const renderStepContent = (step: number) => {
    switch (step) {
      case 0:
        return (
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <FormControl fullWidth required>
                <InputLabel>Customer</InputLabel>
                <Select
                  value={formData.customer_id}
                  onChange={(e) => setFormData({ ...formData, customer_id: e.target.value })}
                  label="Customer"
                >
                  {customers.map((customer) => (
                    <MenuItem key={customer.id} value={customer.id}>
                      {customer.name} - {customer.email}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>PON Port</InputLabel>
                <Select
                  value={formData.pon_port}
                  onChange={(e) => setFormData({ ...formData, pon_port: e.target.value })}
                  label="PON Port"
                >
                  <MenuItem value="pon1">PON 1</MenuItem>
                  <MenuItem value="pon2">PON 2</MenuItem>
                  <MenuItem value="pon3">PON 3</MenuItem>
                  <MenuItem value="pon4">PON 4</MenuItem>
                  <MenuItem value="pon5">PON 5</MenuItem>
                  <MenuItem value="pon6">PON 6</MenuItem>
                  <MenuItem value="pon7">PON 7</MenuItem>
                  <MenuItem value="pon8">PON 8</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                required
                label="ONT ID"
                type="number"
                value={formData.ont_id}
                onChange={(e) => setFormData({ ...formData, ont_id: parseInt(e.target.value) })}
                helperText="Unique ID on the PON port (1-128)"
                inputProps={{ min: 1, max: 128 }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                required
                label="Serial Number"
                value={formData.serial_number}
                onChange={(e) => setFormData({ ...formData, serial_number: e.target.value.toUpperCase() })}
                helperText="ONT Serial Number (printed on device)"
                placeholder="TPLK12345678"
              />
            </Grid>
          </Grid>
        );

      case 1:
        return (
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Service Profile</InputLabel>
                <Select
                  value={formData.service_profile}
                  onChange={(e) => setFormData({ ...formData, service_profile: e.target.value })}
                  label="Service Profile"
                >
                  <MenuItem value="default">Default</MenuItem>
                  <MenuItem value="residential">Residential</MenuItem>
                  <MenuItem value="business">Business</MenuItem>
                  <MenuItem value="premium">Premium</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Bandwidth Profile</InputLabel>
                <Select
                  value={formData.bandwidth_profile}
                  onChange={(e) => setFormData({ ...formData, bandwidth_profile: e.target.value })}
                  label="Bandwidth Profile"
                >
                  <MenuItem value="residential">Residential</MenuItem>
                  <MenuItem value="business_basic">Business Basic</MenuItem>
                  <MenuItem value="business_premium">Business Premium</MenuItem>
                  <MenuItem value="enterprise">Enterprise</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom>VLAN Configuration</Typography>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Management VLAN"
                type="number"
                value={formData.vlan_config.management_vlan}
                onChange={(e) => setFormData({
                  ...formData,
                  vlan_config: {
                    ...formData.vlan_config,
                    management_vlan: parseInt(e.target.value)
                  }
                })}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Service VLAN"
                type="number"
                value={formData.vlan_config.service_vlan}
                onChange={(e) => setFormData({
                  ...formData,
                  vlan_config: {
                    ...formData.vlan_config,
                    service_vlan: parseInt(e.target.value)
                  }
                })}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Internet VLAN"
                type="number"
                value={formData.vlan_config.internet_vlan}
                onChange={(e) => setFormData({
                  ...formData,
                  vlan_config: {
                    ...formData.vlan_config,
                    internet_vlan: parseInt(e.target.value)
                  }
                })}
              />
            </Grid>
          </Grid>
        );

      case 2:
        return (
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.wifi_config.enabled}
                    onChange={(e) => setFormData({
                      ...formData,
                      wifi_config: {
                        ...formData.wifi_config,
                        enabled: e.target.checked
                      }
                    })}
                  />
                }
                label="Enable WiFi"
              />
            </Grid>
            
            {formData.wifi_config.enabled && (
              <>
                <Grid item xs={12}>
                  <Box display="flex" alignItems="center" gap={2}>
                    <TextField
                      fullWidth
                      label="WiFi SSID"
                      value={formData.wifi_config.ssid}
                      onChange={(e) => setFormData({
                        ...formData,
                        wifi_config: {
                          ...formData.wifi_config,
                          ssid: e.target.value
                        }
                      })}
                    />
                    <Button
                      variant="outlined"
                      onClick={generateWiFiCredentials}
                      disabled={!formData.customer_id}
                    >
                      Auto Generate
                    </Button>
                  </Box>
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="WiFi Password"
                    value={formData.wifi_config.password}
                    onChange={(e) => setFormData({
                      ...formData,
                      wifi_config: {
                        ...formData.wifi_config,
                        password: e.target.value
                      }
                    })}
                    helperText="Minimum 8 characters"
                  />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <FormControl fullWidth>
                    <InputLabel>Security</InputLabel>
                    <Select
                      value={formData.wifi_config.security}
                      onChange={(e) => setFormData({
                        ...formData,
                        wifi_config: {
                          ...formData.wifi_config,
                          security: e.target.value
                        }
                      })}
                      label="Security"
                    >
                      <MenuItem value="WPA2">WPA2</MenuItem>
                      <MenuItem value="WPA3">WPA3</MenuItem>
                      <MenuItem value="WPA2/WPA3">WPA2/WPA3 Mixed</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <FormControl fullWidth>
                    <InputLabel>2.4GHz Channel</InputLabel>
                    <Select
                      value={formData.wifi_config.channel_2g}
                      onChange={(e) => setFormData({
                        ...formData,
                        wifi_config: {
                          ...formData.wifi_config,
                          channel_2g: e.target.value
                        }
                      })}
                      label="2.4GHz Channel"
                    >
                      <MenuItem value="auto">Auto</MenuItem>
                      <MenuItem value="1">Channel 1</MenuItem>
                      <MenuItem value="6">Channel 6</MenuItem>
                      <MenuItem value="11">Channel 11</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <FormControl fullWidth>
                    <InputLabel>5GHz Channel</InputLabel>
                    <Select
                      value={formData.wifi_config.channel_5g}
                      onChange={(e) => setFormData({
                        ...formData,
                        wifi_config: {
                          ...formData.wifi_config,
                          channel_5g: e.target.value
                        }
                      })}
                      label="5GHz Channel"
                    >
                      <MenuItem value="auto">Auto</MenuItem>
                      <MenuItem value="36">Channel 36</MenuItem>
                      <MenuItem value="44">Channel 44</MenuItem>
                      <MenuItem value="149">Channel 149</MenuItem>
                      <MenuItem value="157">Channel 157</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </>
            )}
          </Grid>
        );

      case 3:
        const selectedCustomer = customers.find(c => c.id === parseInt(formData.customer_id));
        return (
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" gutterBottom>
                  <Cable sx={{ mr: 1, verticalAlign: 'middle' }} />
                  ONT Configuration Summary
                </Typography>
                <Divider sx={{ my: 2 }} />
                
                <List>
                  <ListItem>
                    <ListItemIcon><NetworkCheck /></ListItemIcon>
                    <ListItemText
                      primary="Customer"
                      secondary={selectedCustomer ? `${selectedCustomer.name} (${selectedCustomer.email})` : 'Not selected'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><Cable /></ListItemIcon>
                    <ListItemText
                      primary="PON Configuration"
                      secondary={`Port: ${formData.pon_port}, ONT ID: ${formData.ont_id}, SN: ${formData.serial_number}`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><Security /></ListItemIcon>
                    <ListItemText
                      primary="Service Profile"
                      secondary={`${formData.service_profile} (${formData.bandwidth_profile})`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><NetworkCheck /></ListItemIcon>
                    <ListItemText
                      primary="VLAN Configuration"
                      secondary={`Mgmt: ${formData.vlan_config.management_vlan}, Service: ${formData.vlan_config.service_vlan}, Internet: ${formData.vlan_config.internet_vlan}`}
                    />
                  </ListItem>
                  {formData.wifi_config.enabled && (
                    <ListItem>
                      <ListItemIcon><Wifi /></ListItemIcon>
                      <ListItemText
                        primary="WiFi Configuration"
                        secondary={`SSID: ${formData.wifi_config.ssid}, Security: ${formData.wifi_config.security}`}
                      />
                    </ListItem>
                  )}
                </List>
              </Paper>
            </Grid>
            
            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                rows={3}
                label="Installation Notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Add any installation notes or special instructions..."
              />
            </Grid>
          </Grid>
        );

      default:
        return null;
    }
  };

  const isStepValid = (step: number) => {
    switch (step) {
      case 0:
        return formData.customer_id && formData.pon_port && formData.ont_id && formData.serial_number;
      case 1:
        return formData.service_profile && formData.bandwidth_profile;
      case 2:
        return !formData.wifi_config.enabled || (formData.wifi_config.ssid && formData.wifi_config.password);
      case 3:
        return true;
      default:
        return false;
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Provision New ONT</DialogTitle>
      <DialogContent>
        <Box sx={{ mt: 2 }}>
          <Stepper activeStep={activeStep}>
            {steps.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}

          <Box sx={{ mt: 3 }}>
            {renderStepContent(activeStep)}
          </Box>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          disabled={activeStep === 0}
          onClick={handleBack}
        >
          Back
        </Button>
        {activeStep === steps.length - 1 ? (
          <Button
            variant="contained"
            onClick={handleProvision}
            disabled={loading || !isStepValid(activeStep)}
          >
            {loading ? 'Provisioning...' : 'Provision ONT'}
          </Button>
        ) : (
          <Button
            variant="contained"
            onClick={handleNext}
            disabled={!isStepValid(activeStep)}
          >
            Next
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default ONTProvisionDialog;