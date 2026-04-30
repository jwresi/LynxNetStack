import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Card,
  CardContent,
  Alert,
  CircularProgress
} from '@mui/material';
import {
  Edit,
  Upload,
  Business,
  PhotoCamera
} from '@mui/icons-material';
import api from '../services/api';

interface OrganizationInfo {
  id?: number;
  name: string;
  logo_url?: string;
  icon_url?: string;
  tagline?: string;
  primary_color?: string;
  secondary_color?: string;
}

interface OrganizationBrandingProps {
  variant?: 'header' | 'sidebar';
  showEdit?: boolean;
}

const OrganizationBranding: React.FC<OrganizationBrandingProps> = ({ 
  variant = 'header', 
  showEdit = false 
}) => {
  const [orgInfo, setOrgInfo] = useState<OrganizationInfo>({
    name: 'Your Organization',
    tagline: 'Customer Relationship Management'
  });
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [iconPreview, setIconPreview] = useState<string | null>(null);

  useEffect(() => {
    loadOrganizationInfo();
  }, []);

  const loadOrganizationInfo = async () => {
    try {
      const response = await api.get('/api/v1/organization/info');
      if (response.data) {
        setOrgInfo(response.data);
      }
    } catch (err) {
      console.error('Failed to load organization info:', err);
      // Keep default values if API fails
    }
  };

  const handleEditClick = () => {
    setEditDialogOpen(true);
    setLogoPreview(null);
    setIconPreview(null);
    setLogoFile(null);
    setIconFile(null);
    setError(null);
  };

  const handleLogoUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) { // 5MB limit
        setError('Logo file size must be less than 5MB');
        return;
      }
      if (!file.type.startsWith('image/')) {
        setError('Please select a valid image file');
        return;
      }
      setLogoFile(file);
      const reader = new FileReader();
      reader.onload = (e) => setLogoPreview(e.target?.result as string);
      reader.readAsDataURL(file);
      setError(null);
    }
  };

  const handleIconUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (file.size > 2 * 1024 * 1024) { // 2MB limit
        setError('Icon file size must be less than 2MB');
        return;
      }
      if (!file.type.startsWith('image/')) {
        setError('Please select a valid image file');
        return;
      }
      setIconFile(file);
      const reader = new FileReader();
      reader.onload = (e) => setIconPreview(e.target?.result as string);
      reader.readAsDataURL(file);
      setError(null);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('name', orgInfo.name);
      formData.append('tagline', orgInfo.tagline || '');
      formData.append('primary_color', orgInfo.primary_color || '#1976d2');
      formData.append('secondary_color', orgInfo.secondary_color || '#1565c0');

      if (logoFile) {
        formData.append('logo', logoFile);
      }
      if (iconFile) {
        formData.append('icon', iconFile);
      }

      const response = await api.post('/api/v1/organization/info', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data) {
        setOrgInfo(response.data);
        setEditDialogOpen(false);
        setLogoFile(null);
        setIconFile(null);
        setLogoPreview(null);
        setIconPreview(null);
      }
    } catch (err: any) {
      setError(err?.response?.data?.message || 'Failed to save organization info');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setEditDialogOpen(false);
    setLogoFile(null);
    setIconFile(null);
    setLogoPreview(null);
    setIconPreview(null);
    setError(null);
  };

  const getFontStyle = () => {
    if (variant === 'header') {
      return {
        fontFamily: '"Playfair Display", "Times New Roman", serif',
        fontSize: '2.8rem',
        fontWeight: 700,
        background: `linear-gradient(135deg, ${orgInfo.primary_color || '#1976d2'}, ${orgInfo.secondary_color || '#1565c0'})`,
        backgroundClip: 'text',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        textShadow: '0 4px 8px rgba(0,0,0,0.15)',
        letterSpacing: '1px',
        textTransform: 'uppercase' as const,
        lineHeight: 1.2
      };
    }
    return {
      fontFamily: '"Playfair Display", "Times New Roman", serif',
      fontSize: '1.4rem',
      fontWeight: 600,
      color: orgInfo.primary_color || '#1976d2',
      letterSpacing: '0.5px',
      textTransform: 'capitalize' as const
    };
  };

  if (variant === 'sidebar') {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Box sx={{
          width: 40,
          height: 40,
          borderRadius: 2,
          background: orgInfo.icon_url ? 'transparent' : 
            `linear-gradient(45deg, ${orgInfo.primary_color || '#1976d2'}, ${orgInfo.secondary_color || '#1565c0'})`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: orgInfo.icon_url ? 'none' : '0 4px 8px rgba(25, 118, 210, 0.3)',
          overflow: 'hidden'
        }}>
          {orgInfo.icon_url ? (
            <img 
              src={orgInfo.icon_url} 
              alt="Organization Icon"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold' }}>
              {orgInfo.name.charAt(0).toUpperCase()}
            </Typography>
          )}
        </Box>
        <Box>
          <Typography variant="h6" sx={getFontStyle()}>
            {orgInfo.name}
          </Typography>
          <Typography variant="caption" sx={{ 
            color: 'text.secondary',
            fontSize: '0.75rem'
          }}>
            {orgInfo.tagline}
          </Typography>
        </Box>
      </Box>
    );
  }

  // Header variant
  return (
    <Box>
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: 3,
        mb: 2
      }}>
        {/* Logo */}
        <Box sx={{
          width: 80,
          height: 80,
          borderRadius: 3,
          background: orgInfo.logo_url ? 'transparent' : 
            `linear-gradient(45deg, ${orgInfo.primary_color || '#1976d2'}, ${orgInfo.secondary_color || '#1565c0'})`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: orgInfo.logo_url ? '0 4px 12px rgba(0,0,0,0.15)' : '0 4px 12px rgba(25, 118, 210, 0.3)',
          overflow: 'hidden',
          position: 'relative'
        }}>
          {orgInfo.logo_url ? (
            <img 
              src={orgInfo.logo_url} 
              alt="Organization Logo"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : (
            <Business sx={{ fontSize: 40, color: 'white' }} />
          )}
        </Box>

        {/* Organization Name and Tagline */}
        <Box sx={{ flex: 1 }}>
          <Typography variant="h3" sx={getFontStyle()}>
            {orgInfo.name}
          </Typography>
          <Typography 
            variant="h6" 
            sx={{ 
              color: 'text.secondary',
              fontStyle: 'italic',
              mt: 1
            }}
          >
            {orgInfo.tagline}
          </Typography>
        </Box>

        {/* Edit Button */}
        {showEdit && (
          <IconButton 
            onClick={handleEditClick}
            sx={{ 
              bgcolor: 'primary.main', 
              color: 'white',
              '&:hover': { bgcolor: 'primary.dark' }
            }}
          >
            <Edit />
          </IconButton>
        )}
      </Box>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onClose={handleCancel} maxWidth="md" fullWidth>
        <DialogTitle>Edit Organization Branding</DialogTitle>
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          
          <Box sx={{ mt: 2 }}>
            <TextField
              fullWidth
              label="Organization Name"
              value={orgInfo.name}
              onChange={(e) => setOrgInfo({ ...orgInfo, name: e.target.value })}
              margin="normal"
              required
            />
            
            <TextField
              fullWidth
              label="Tagline"
              value={orgInfo.tagline || ''}
              onChange={(e) => setOrgInfo({ ...orgInfo, tagline: e.target.value })}
              margin="normal"
              placeholder="e.g., Customer Relationship Management"
            />

            <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
              <TextField
                label="Primary Color"
                type="color"
                value={orgInfo.primary_color || '#1976d2'}
                onChange={(e) => setOrgInfo({ ...orgInfo, primary_color: e.target.value })}
                sx={{ flex: 1 }}
              />
              <TextField
                label="Secondary Color"
                type="color"
                value={orgInfo.secondary_color || '#1565c0'}
                onChange={(e) => setOrgInfo({ ...orgInfo, secondary_color: e.target.value })}
                sx={{ flex: 1 }}
              />
            </Box>

            {/* Logo Upload */}
            <Card sx={{ mt: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Organization Logo
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box sx={{
                    width: 100,
                    height: 100,
                    border: '2px dashed #ccc',
                    borderRadius: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden'
                  }}>
                    {logoPreview ? (
                      <img 
                        src={logoPreview} 
                        alt="Logo Preview"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : orgInfo.logo_url ? (
                      <img 
                        src={orgInfo.logo_url} 
                        alt="Current Logo"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <PhotoCamera sx={{ fontSize: 40, color: '#ccc' }} />
                    )}
                  </Box>
                  <Box>
                    <input
                      accept="image/*"
                      style={{ display: 'none' }}
                      id="logo-upload"
                      type="file"
                      onChange={handleLogoUpload}
                    />
                    <label htmlFor="logo-upload">
                      <Button
                        variant="outlined"
                        component="span"
                        startIcon={<Upload />}
                      >
                        Upload Logo
                      </Button>
                    </label>
                    <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                      Recommended: 512x512px, max 5MB
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>

            {/* Icon Upload */}
            <Card sx={{ mt: 2 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Sidebar Icon
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box sx={{
                    width: 60,
                    height: 60,
                    border: '2px dashed #ccc',
                    borderRadius: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden'
                  }}>
                    {iconPreview ? (
                      <img 
                        src={iconPreview} 
                        alt="Icon Preview"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : orgInfo.icon_url ? (
                      <img 
                        src={orgInfo.icon_url} 
                        alt="Current Icon"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <PhotoCamera sx={{ fontSize: 24, color: '#ccc' }} />
                    )}
                  </Box>
                  <Box>
                    <input
                      accept="image/*"
                      style={{ display: 'none' }}
                      id="icon-upload"
                      type="file"
                      onChange={handleIconUpload}
                    />
                    <label htmlFor="icon-upload">
                      <Button
                        variant="outlined"
                        component="span"
                        startIcon={<Upload />}
                        size="small"
                      >
                        Upload Icon
                      </Button>
                    </label>
                    <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                      Recommended: 64x64px, max 2MB
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancel}>Cancel</Button>
          <Button 
            onClick={handleSave} 
            variant="contained"
            disabled={loading || !orgInfo.name.trim()}
            startIcon={loading ? <CircularProgress size={16} /> : undefined}
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default OrganizationBranding;