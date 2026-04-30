import React from 'react';
import {
  AppBar,
  Toolbar,
  IconButton,
  Typography,
  Box,
  TextField,
  InputAdornment,
  Chip,
  Badge,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Avatar,
  useTheme,
  useMediaQuery,
  Drawer
} from '@mui/material';
import {
  Menu as MenuIcon,
  Search as SearchIcon,
  Notifications,
  Settings,
  Help,
  AccountCircle,
  Refresh,
  FilterList,
  CloudOff,
  Wifi,
  Speed,
  Person,
  Security,
  Logout
} from '@mui/icons-material';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

interface TopNavbarProps {
  sidebarOpen: boolean;
  onMenuToggle: () => void;
}

const TopNavbar: React.FC<TopNavbarProps> = ({ sidebarOpen, onMenuToggle }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [searchValue, setSearchValue] = React.useState('');
  const [notificationAnchor, setNotificationAnchor] = React.useState<null | HTMLElement>(null);
  const [profileMenuAnchor, setProfileMenuAnchor] = React.useState<null | HTMLElement>(null);
  const [settingsDialogOpen, setSettingsDialogOpen] = React.useState(false);
  const [helpDialogOpen, setHelpDialogOpen] = React.useState(false);
  const [searchDrawerOpen, setSearchDrawerOpen] = React.useState(false);

  const handleNotificationClick = (event: React.MouseEvent<HTMLElement>) => {
    setNotificationAnchor(event.currentTarget);
  };

  const handleNotificationClose = () => {
    setNotificationAnchor(null);
  };

  const handleProfileClick = (event: React.MouseEvent<HTMLElement>) => {
    setProfileMenuAnchor(event.currentTarget);
  };

  const handleProfileClose = () => {
    setProfileMenuAnchor(null);
  };

  const handleRefresh = () => {
    window.location.reload();
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
    handleProfileClose();
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchValue.trim()) {
      // Navigate to search results or handle search logic
      console.log('Searching for:', searchValue);
    }
  };

  return (
    <AppBar 
      position="fixed" 
      sx={{ 
        zIndex: (theme) => theme.zIndex.drawer + 1,
        bgcolor: 'white',
        color: 'text.primary',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        borderBottom: '1px solid #e0e0e0'
      }}
    >
      <Toolbar sx={{ gap: 2 }}>
        {/* Menu Toggle */}
        <IconButton
          edge="start"
          onClick={onMenuToggle}
          sx={{ 
            color: 'text.primary',
            '&:hover': {
              bgcolor: 'rgba(0, 0, 0, 0.04)'
            }
          }}
        >
          <MenuIcon />
        </IconButton>

        {/* Search Bar - Desktop */}
        {!isMobile && (
          <Box component="form" onSubmit={handleSearchSubmit}>
            <TextField
              placeholder="Search customers, tickets, orders..."
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              size="small"
              sx={{ 
                minWidth: 300,
                '& .MuiOutlinedInput-root': {
                  backgroundColor: '#f5f5f5',
                  '&:hover': {
                    backgroundColor: '#eeeeee',
                  },
                  '&.Mui-focused': {
                    backgroundColor: 'white',
                  }
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ color: 'text.secondary' }} />
                  </InputAdornment>
                ),
              }}
            />
          </Box>
        )}

        {/* Search Button - Mobile */}
        {isMobile && (
          <IconButton
            onClick={() => setSearchDrawerOpen(true)}
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <SearchIcon />
          </IconButton>
        )}

        {/* Status Indicators - Replace with real data */}
        <Box sx={{ display: 'flex', gap: 1, flex: 1 }}>
          {/* Status chips will be populated from API data */}
        </Box>

        {/* Right Side Actions */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {/* Refresh Button */}
          <IconButton
            onClick={handleRefresh}
            title="Refresh Page"
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <Refresh />
          </IconButton>

          {/* Filter Button */}
          <IconButton
            onClick={() => {
              // TODO: Implement global filter functionality
              console.log('Filter functionality not yet implemented');
            }}
            title="Filters (Coming Soon)"
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <FilterList />
          </IconButton>

          {/* Notifications */}
          <IconButton
            onClick={handleNotificationClick}
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <Badge badgeContent={0} color="error">
              <Notifications />
            </Badge>
          </IconButton>

          <Menu
            anchorEl={notificationAnchor}
            open={Boolean(notificationAnchor)}
            onClose={handleNotificationClose}
            PaperProps={{
              sx: {
                mt: 1,
                minWidth: 320,
                maxHeight: 400
              }
            }}
          >
            <Box sx={{ p: 2, borderBottom: '1px solid #e0e0e0' }}>
              <Typography variant="h6">Notifications</Typography>
            </Box>
            <MenuItem disabled>
              <ListItemText 
                primary="No notifications" 
                secondary="You're all caught up!"
                sx={{ textAlign: 'center', color: 'text.secondary' }}
              />
            </MenuItem>
          </Menu>

          {/* Help Button */}
          <IconButton
            onClick={() => setHelpDialogOpen(true)}
            title="Help & Support"
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <Help />
          </IconButton>

          {/* Settings Button */}
          <IconButton
            onClick={() => setSettingsDialogOpen(true)}
            title="Settings"
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <Settings />
          </IconButton>

          {/* Profile Button */}
          <IconButton
            onClick={handleProfileClick}
            title="User Profile"
            sx={{ 
              color: 'text.secondary',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.04)'
              }
            }}
          >
            <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main' }}>
              {user?.username?.[0]?.toUpperCase() || 'U'}
            </Avatar>
          </IconButton>
        </Box>
      </Toolbar>

      {/* Profile Menu */}
      <Menu
        anchorEl={profileMenuAnchor}
        open={Boolean(profileMenuAnchor)}
        onClose={handleProfileClose}
        PaperProps={{
          sx: {
            mt: 1,
            minWidth: 200
          }
        }}
      >
        <Box sx={{ p: 2, borderBottom: '1px solid #e0e0e0' }}>
          <Typography variant="subtitle1">{user?.username || 'User'}</Typography>
          <Typography variant="body2" color="text.secondary">
            {user?.email || 'No email configured'}
          </Typography>
        </Box>
        <MenuItem onClick={() => { handleProfileClose(); navigate('/profile'); }}>
          <ListItemIcon>
            <Person />
          </ListItemIcon>
          <ListItemText primary="Profile" />
        </MenuItem>
        <MenuItem onClick={() => { handleProfileClose(); setSettingsDialogOpen(true); }}>
          <ListItemIcon>
            <Settings />
          </ListItemIcon>
          <ListItemText primary="Settings" />
        </MenuItem>
        <MenuItem onClick={() => { handleProfileClose(); navigate('/users'); }}>
          <ListItemIcon>
            <Security />
          </ListItemIcon>
          <ListItemText primary="User Management" />
        </MenuItem>
        <Divider />
        <MenuItem onClick={handleLogout}>
          <ListItemIcon>
            <Logout color="error" />
          </ListItemIcon>
          <ListItemText primary="Logout" sx={{ color: 'error.main' }} />
        </MenuItem>
      </Menu>

      {/* Settings Dialog */}
      <Dialog open={settingsDialogOpen} onClose={() => setSettingsDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>System Settings</DialogTitle>
        <DialogContent>
          <Box sx={{ py: 2 }}>
            <Typography variant="h6" gutterBottom>User Preferences</Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Configure your personal settings and preferences.
            </Typography>
            
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>System Configuration</Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Access system-wide configuration options. (Admin access required)
            </Typography>
            
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>Network Settings</Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Configure network monitoring thresholds and alert preferences.
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSettingsDialogOpen(false)}>Close</Button>
          <Button variant="contained" onClick={() => { setSettingsDialogOpen(false); navigate('/users'); }}>
            Go to User Management
          </Button>
        </DialogActions>
      </Dialog>

      {/* Help Dialog */}
      <Dialog open={helpDialogOpen} onClose={() => setHelpDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Help & Support</DialogTitle>
        <DialogContent>
          <Box sx={{ py: 2 }}>
            <Typography variant="h6" gutterBottom>Quick Start Guide</Typography>
            <Typography variant="body2" paragraph>
              • Use the sidebar to navigate between different sections
              • Search for customers, tickets, or orders using the search bar
              • Monitor system status using the chips in the top bar
              • Access notifications through the bell icon
            </Typography>
            
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>Common Tasks</Typography>
            <Typography variant="body2" paragraph>
              • Add new customers: Customer Management → Add Customer
              • Create service orders: Operations → Service Orders
              • Monitor network: Network Management → Network Monitoring
              • Generate reports: Reports & Analytics
            </Typography>
            
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>Support</Typography>
            <Typography variant="body2" paragraph>
              For technical support, please contact your system administrator or
              refer to the LynxCRM documentation.
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpDialogOpen(false)}>Close</Button>
          <Button variant="contained" onClick={() => { setHelpDialogOpen(false); navigate('/tickets'); }}>
            Create Support Ticket
          </Button>
        </DialogActions>
      </Dialog>
    </AppBar>
  );
};

export default TopNavbar;