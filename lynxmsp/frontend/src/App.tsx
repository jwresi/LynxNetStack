import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Box, CssBaseline, useTheme, useMediaQuery } from '@mui/material';
import Sidebar from './components/Sidebar';
import TopNavbar from './components/TopNavbar';
import Login from './pages/Login';
import CompanySetup from './pages/CompanySetup';
import Dashboard from './pages/Dashboard';
import Customers from './pages/Customers';
import CustomerDetail from './pages/CustomerDetail';
import Invoices from './pages/Invoices';
import Tickets from './pages/Tickets';
import NetworkTopology from './pages/NetworkTopology';
import RouterManagement from './pages/RouterManagement';
import CGNATManagement from './pages/CGNATManagement';
import ServicePlans from './pages/ServicePlans';
import UserManagement from './pages/UserManagement';
import TPLinkManagement from './pages/TPLinkManagement';
import IPv6Management from './pages/IPv6Management';
import NetworkDiscovery from './pages/NetworkDiscovery';
import Profile from './pages/Profile';
import UnifiedDashboard from './components/UnifiedDashboard';
import { AuthProvider, useAuth } from './hooks/useAuth';

const DRAWER_WIDTH = 280;

function AppContent() {
  const { isAuthenticated } = useAuth();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [sidebarOpen, setSidebarOpen] = useState(!isMobile);

  useEffect(() => {
    setSidebarOpen(!isMobile);
  }, [isMobile]);

  const handleSidebarToggle = () => {
    setSidebarOpen(!sidebarOpen);
  };

  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/setup" element={<CompanySetup />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <CssBaseline />
      
      {/* Top Navigation */}
      <TopNavbar 
        sidebarOpen={sidebarOpen} 
        onMenuToggle={handleSidebarToggle} 
      />
      
      {/* Sidebar */}
      <Sidebar 
        open={sidebarOpen} 
        onClose={() => setSidebarOpen(false)} 
      />
      
      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          backgroundColor: '#f8f9fa',
          minHeight: '100vh',
          pt: '64px', // Use padding-top for AppBar height
          ml: !isMobile && sidebarOpen ? `${DRAWER_WIDTH}px` : 0, // Only use margin-left on desktop
          pl: !isMobile && sidebarOpen ? 2 : 3, // Add padding-left for proper spacing
          pr: 3, // Add padding-right for consistent spacing
          transition: theme.transitions.create(['margin-left', 'padding-left'], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.standard,
          }),
        }}
      >
        <Box sx={{ py: 2 }}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<UnifiedDashboard />} />
            <Route path="/dashboard/legacy" element={<Dashboard />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/customers/new" element={<Customers />} />
            <Route path="/customers/prospects" element={<Customers />} />
            <Route path="/customers/suspended" element={<Customers />} />
            <Route path="/customers/:id" element={<CustomerDetail />} />
            <Route path="/invoices" element={<Invoices />} />
            <Route path="/payments" element={<Invoices />} />
            <Route path="/payment-methods" element={<Invoices />} />
            <Route path="/billing-reports" element={<Invoices />} />
            <Route path="/tickets" element={<Tickets />} />
            <Route path="/service-orders" element={<Tickets />} />
            <Route path="/installers" element={<Tickets />} />
            <Route path="/contractors" element={<Tickets />} />
            
            {/* Network Management Routes */}
            <Route path="/network-topology" element={<NetworkTopology />} />
            <Route path="/router-management" element={<RouterManagement />} />
            <Route path="/tplink-management" element={<TPLinkManagement />} />
            <Route path="/olt-management" element={<NetworkTopology />} />
            <Route path="/cgnat-management" element={<CGNATManagement />} />
            <Route path="/ipv6-management" element={<IPv6Management />} />
            <Route path="/ip-management" element={<NetworkTopology />} />
            <Route path="/network-discovery" element={<NetworkDiscovery />} />
            <Route path="/monitoring" element={<Dashboard />} />
            
            {/* Infrastructure Routes */}
            <Route path="/sites" element={<NetworkTopology />} />
            <Route path="/equipment" element={<NetworkTopology />} />
            <Route path="/fiber-management" element={<NetworkTopology />} />
            
            {/* Service Plans */}
            <Route path="/service-plans" element={<ServicePlans />} />
            
            {/* User Management */}
            <Route path="/users" element={<UserManagement />} />
            <Route path="/roles" element={<UserManagement />} />
            <Route path="/profile" element={<Profile />} />
            
            {/* Reports */}
            <Route path="/reports/revenue" element={<Dashboard />} />
            <Route path="/reports/network" element={<Dashboard />} />
            <Route path="/reports/customers" element={<Dashboard />} />
          </Routes>
        </Box>
      </Box>
    </Box>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;