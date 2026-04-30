import React from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  IconButton,
  Menu,
  MenuItem,
  Divider,
  ListItemIcon,
  ListItemText
} from '@mui/material';
import {
  Dashboard,
  People,
  Receipt,
  Support,
  AccountCircle,
  Router as RouterIcon,
  NetworkCheck,
  Speed,
  Cable,
  Business,
  Settings,
  Memory
} from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

function Navbar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);
  const [networkMenuAnchor, setNetworkMenuAnchor] = React.useState<null | HTMLElement>(null);

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleNetworkMenu = (event: React.MouseEvent<HTMLElement>) => {
    setNetworkMenuAnchor(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleNetworkMenuClose = () => {
    setNetworkMenuAnchor(null);
  };

  const handleLogout = () => {
    logout();
    handleClose();
  };

  const crmItems = [
    { path: '/dashboard', label: 'Dashboard', icon: <Dashboard /> },
    { path: '/customers', label: 'Customers', icon: <People /> },
    { path: '/invoices', label: 'Invoices', icon: <Receipt /> },
    { path: '/tickets', label: 'Support', icon: <Support /> },
  ];

  const networkItems = [
    { path: '/network-topology', label: 'Network Topology', icon: <NetworkCheck /> },
    { path: '/router-management', label: 'Router Management', icon: <RouterIcon /> },
    { path: '/cgnat-management', label: 'CGNAT Management', icon: <Speed /> },
    { path: '/ipv6-management', label: 'IPv6 Management', icon: <Memory /> },
    { path: '/ip-management', label: 'IP Management', icon: <Cable /> },
    { path: '/sites', label: 'Sites', icon: <Business /> },
  ];

  const isNetworkPath = networkItems.some(item => location.pathname === item.path);

  return (
    <AppBar position="static" sx={{ background: 'linear-gradient(45deg, #1976d2, #1565c0)' }}>
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
          LynxCRM
        </Typography>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {/* CRM Navigation */}
          {crmItems.map((item) => (
            <Button
              key={item.path}
              color="inherit"
              component={Link}
              to={item.path}
              startIcon={item.icon}
              sx={{
                backgroundColor: location.pathname === item.path ? 'rgba(255, 255, 255, 0.15)' : 'transparent',
                '&:hover': {
                  backgroundColor: 'rgba(255, 255, 255, 0.1)'
                },
                borderRadius: 2,
                px: 2
              }}
            >
              {item.label}
            </Button>
          ))}

          {/* Network Management Dropdown */}
          <Button
            color="inherit"
            onClick={handleNetworkMenu}
            startIcon={<NetworkCheck />}
            sx={{
              backgroundColor: isNetworkPath ? 'rgba(255, 255, 255, 0.15)' : 'transparent',
              '&:hover': {
                backgroundColor: 'rgba(255, 255, 255, 0.1)'
              },
              borderRadius: 2,
              px: 2
            }}
          >
            Network
          </Button>
          <Menu
            anchorEl={networkMenuAnchor}
            open={Boolean(networkMenuAnchor)}
            onClose={handleNetworkMenuClose}
            PaperProps={{
              sx: {
                mt: 1,
                minWidth: 220,
                '& .MuiMenuItem-root': {
                  px: 2,
                  py: 1
                }
              }
            }}
          >
            {networkItems.map((item) => (
              <MenuItem
                key={item.path}
                component={Link}
                to={item.path}
                onClick={handleNetworkMenuClose}
                sx={{
                  backgroundColor: location.pathname === item.path ? 'action.selected' : 'transparent'
                }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>
                  {item.icon}
                </ListItemIcon>
                <ListItemText primary={item.label} />
              </MenuItem>
            ))}
          </Menu>
          
          {/* User Menu */}
          <IconButton
            size="large"
            aria-label="account of current user"
            aria-controls="menu-appbar"
            aria-haspopup="true"
            onClick={handleMenu}
            color="inherit"
            sx={{
              ml: 1,
              '&:hover': {
                backgroundColor: 'rgba(255, 255, 255, 0.1)'
              }
            }}
          >
            <AccountCircle />
          </IconButton>
          <Menu
            id="menu-appbar"
            anchorEl={anchorEl}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'right',
            }}
            keepMounted
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
            open={Boolean(anchorEl)}
            onClose={handleClose}
            PaperProps={{
              sx: {
                mt: 1,
                minWidth: 150
              }
            }}
          >
            <MenuItem onClick={handleClose}>
              <ListItemIcon>
                <AccountCircle fontSize="small" />
              </ListItemIcon>
              <ListItemText primary={user?.username || 'User'} />
            </MenuItem>
            <Divider />
            <MenuItem onClick={handleClose}>
              <ListItemIcon>
                <Settings fontSize="small" />
              </ListItemIcon>
              <ListItemText primary="Settings" />
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <Receipt fontSize="small" />
              </ListItemIcon>
              <ListItemText primary="Logout" />
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
}

export default Navbar;