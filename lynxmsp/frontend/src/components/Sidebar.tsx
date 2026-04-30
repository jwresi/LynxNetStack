import React, { useState } from 'react';
import {
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Collapse,
  Box,
  Badge,
  useTheme,
  useMediaQuery
} from '@mui/material';
import {
  Dashboard,
  People,
  Receipt,
  Support,
  NetworkCheck,
  Router as RouterIcon,
  Speed,
  Cable,
  Business,
  Memory,
  ExpandLess,
  ExpandMore,
  FiberManualRecord,
  Assignment,
  MonitorHeart,
  Security,
  AccountBalance,
  Engineering,
  Build,
  PersonAdd,
  Group,
  TrendingUp,
  BarChart,
  Inventory,
  LocationOn,
  Satellite,
  Hub
} from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import OrganizationBranding from './OrganizationBranding';

const DRAWER_WIDTH = 280;

interface MenuItem {
  id: string;
  label: string;
  icon: React.ReactElement;
  path?: string;
  children?: MenuItem[];
  badge?: number;
}

const menuItems: MenuItem[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: <Dashboard />,
    path: '/dashboard'
  },
  {
    id: 'customers',
    label: 'Customer Management',
    icon: <People />,
    children: [
      { id: 'customers-list', label: 'All Customers', icon: <People />, path: '/customers' },
      { id: 'customers-add', label: 'Add Customer', icon: <PersonAdd />, path: '/customers/new' },
      { id: 'customers-prospects', label: 'Prospects', icon: <TrendingUp />, path: '/customers/prospects' },
      { id: 'customers-suspended', label: 'Suspended', icon: <FiberManualRecord />, path: '/customers/suspended' }
    ]
  },
  {
    id: 'network',
    label: 'Network Management',
    icon: <NetworkCheck />,
    children: [
      { id: 'network-topology', label: 'Network Topology', icon: <NetworkCheck />, path: '/network-topology' },
      { id: 'router-management', label: 'Router Management', icon: <RouterIcon />, path: '/router-management' },
      { id: 'tplink-management', label: 'TPLink OLT/ONT', icon: <Cable />, path: '/tplink-management' },
      { id: 'olt-management', label: 'OLT/ONU Management', icon: <Satellite />, path: '/olt-management' },
      { id: 'cgnat-management', label: 'CGNAT Management', icon: <Speed />, path: '/cgnat-management' },
      { id: 'ipv6-management', label: 'IPv6 Management', icon: <Memory />, path: '/ipv6-management' },
      { id: 'ip-management', label: 'IP Management', icon: <Cable />, path: '/ip-management' },
      { id: 'monitoring', label: 'Network Monitoring', icon: <MonitorHeart />, path: '/monitoring' }
    ]
  },
  {
    id: 'infrastructure',
    label: 'Infrastructure',
    icon: <Business />,
    children: [
      { id: 'sites', label: 'Sites & Locations', icon: <LocationOn />, path: '/sites' },
      { id: 'equipment', label: 'Equipment Inventory', icon: <Inventory />, path: '/equipment' },
      { id: 'fiber-management', label: 'Fiber Management', icon: <Hub />, path: '/fiber-management' }
    ]
  },
  {
    id: 'service-plans',
    label: 'Service Plans',
    icon: <Assignment />,
    path: '/service-plans'
  },
  {
    id: 'billing',
    label: 'Billing & Payments',
    icon: <AccountBalance />,
    children: [
      { id: 'invoices', label: 'Invoices', icon: <Receipt />, path: '/invoices' },
      { id: 'payments', label: 'Payments', icon: <AccountBalance />, path: '/payments' },
      { id: 'payment-methods', label: 'Payment Methods', icon: <Security />, path: '/payment-methods' },
      { id: 'billing-reports', label: 'Billing Reports', icon: <BarChart />, path: '/billing-reports' }
    ]
  },
  {
    id: 'operations',
    label: 'Operations',
    icon: <Engineering />,
    children: [
      { id: 'service-orders', label: 'Service Orders', icon: <Assignment />, path: '/service-orders', badge: 5 },
      { id: 'tickets', label: 'Support Tickets', icon: <Support />, path: '/tickets', badge: 12 },
      { id: 'installers', label: 'Installers', icon: <Build />, path: '/installers' },
      { id: 'contractors', label: 'Contractors', icon: <Engineering />, path: '/contractors' }
    ]
  },
  {
    id: 'users',
    label: 'User Management',
    icon: <Group />,
    children: [
      { id: 'users-list', label: 'All Users', icon: <Group />, path: '/users' },
      { id: 'roles-permissions', label: 'Roles & Permissions', icon: <Security />, path: '/roles' }
    ]
  },
  {
    id: 'reports',
    label: 'Reports & Analytics',
    icon: <BarChart />,
    children: [
      { id: 'revenue-reports', label: 'Revenue Reports', icon: <TrendingUp />, path: '/reports/revenue' },
      { id: 'network-reports', label: 'Network Reports', icon: <NetworkCheck />, path: '/reports/network' },
      { id: 'customer-reports', label: 'Customer Reports', icon: <People />, path: '/reports/customers' }
    ]
  }
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ open, onClose }) => {
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set(['network', 'customers']));

  const handleItemExpand = (itemId: string) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(itemId)) {
      newExpanded.delete(itemId);
    } else {
      newExpanded.add(itemId);
    }
    setExpandedItems(newExpanded);
  };

  const isCurrentPath = (path: string) => {
    return location.pathname === path;
  };

  const isParentActive = (item: MenuItem) => {
    if (item.path && isCurrentPath(item.path)) return true;
    if (item.children) {
      return item.children.some(child => child.path && isCurrentPath(child.path));
    }
    return false;
  };

  const handleLinkClick = () => {
    if (isMobile) {
      onClose();
    }
  };

  const renderMenuItem = (item: MenuItem, depth: number = 0) => {
    const hasChildren = item.children && item.children.length > 0;
    const isExpanded = expandedItems.has(item.id);
    const isActive = isParentActive(item);
    const paddingLeft = depth === 0 ? 2 : 4;

    return (
      <React.Fragment key={item.id}>
        <ListItem disablePadding>
          <ListItemButton
            component={!hasChildren && item.path ? Link : 'div'}
            to={!hasChildren && item.path ? item.path : ''}
            onClick={hasChildren ? () => handleItemExpand(item.id) : (!hasChildren && item.path ? handleLinkClick : undefined)}
            sx={{
              pl: paddingLeft,
              py: 1.5,
              minHeight: 48,
              backgroundColor: isActive ? 'rgba(25, 118, 210, 0.08)' : 'transparent',
              borderRight: isActive ? '3px solid #1976d2' : '3px solid transparent',
              '&:hover': {
                backgroundColor: 'rgba(25, 118, 210, 0.04)',
              }
            }}
          >
            <ListItemIcon sx={{ 
              minWidth: 40, 
              color: isActive ? 'primary.main' : 'text.secondary' 
            }}>
              {item.icon}
            </ListItemIcon>
            <ListItemText 
              primary={item.label} 
              primaryTypographyProps={{
                fontSize: '0.875rem',
                fontWeight: isActive ? 600 : 400,
                color: isActive ? 'primary.main' : 'text.primary'
              }}
            />
            {item.badge && (
              <Badge 
                badgeContent={item.badge} 
                color="error" 
                sx={{ mr: hasChildren ? 1 : 0 }}
              />
            )}
            {hasChildren && (
              isExpanded ? <ExpandLess /> : <ExpandMore />
            )}
          </ListItemButton>
        </ListItem>
        {hasChildren && (
          <Collapse in={isExpanded} timeout="auto" unmountOnExit>
            <List component="div" disablePadding>
              {item.children!.map((child) => renderMenuItem(child, depth + 1))}
            </List>
          </Collapse>
        )}
      </React.Fragment>
    );
  };

  const drawerContent = (
    <Box sx={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      bgcolor: '#fafafa'
    }}>
      {/* Logo and Header */}
      <Box sx={{ 
        p: 3, 
        borderBottom: '1px solid #e0e0e0',
        bgcolor: 'white'
      }}>
        <OrganizationBranding variant="sidebar" />
      </Box>

      {/* Navigation Menu */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        <List sx={{ py: 1 }}>
          {menuItems.map((item) => renderMenuItem(item))}
        </List>
      </Box>
    </Box>
  );

  return (
    <Drawer
      variant={isMobile ? "temporary" : "persistent"}
      anchor="left"
      open={open}
      onClose={onClose}
      ModalProps={{
        keepMounted: true, // Better open performance on mobile
      }}
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
          borderRight: '1px solid #e0e0e0',
          boxShadow: isMobile ? '4px 0 16px rgba(0,0,0,0.15)' : '2px 0 8px rgba(0,0,0,0.1)',
          position: 'fixed',
          top: isMobile ? 0 : '64px', // Full height on mobile, below AppBar on desktop
          height: isMobile ? '100vh' : 'calc(100vh - 64px)',
          zIndex: isMobile ? 1300 : 1200, // Higher z-index on mobile to appear above AppBar
        },
      }}
    >
      {drawerContent}
    </Drawer>
  );
};

export default Sidebar;