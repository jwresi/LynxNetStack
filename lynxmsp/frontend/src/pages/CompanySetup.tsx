import React, { useState, useEffect } from 'react';
import {
    Box,
    Container,
    Typography,
    Card,
    CardContent,
    Grid,
    TextField,
    Button,
    Tabs,
    Tab,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Switch,
    FormControlLabel,
    Alert,
    Snackbar,
    IconButton,
    InputAdornment,
    Divider,
    Chip,
    CircularProgress
} from '@mui/material';
import {
    Visibility,
    VisibilityOff,
    Save,
    Refresh,
    Settings as SettingsIcon,
    Api as ApiIcon,
    Router as NetworkIcon,
    Notifications as NotificationsIcon,
    Business as BusinessIcon
} from '@mui/icons-material';
import { api } from '../services/api';

interface CompanySetting {
    id: number;
    setting_key: string;
    setting_value: string;
    setting_type: string;
    category: string;
    description: string;
    is_encrypted: boolean;
    company_id: number;
    created_at: string;
    updated_at: string;
}

interface CompanySettingsResponse {
    settings: CompanySetting[];
    categories: string[];
}

interface TabPanelProps {
    children?: React.ReactNode;
    index: number;
    value: number;
}

function TabPanel(props: TabPanelProps) {
    const { children, value, index, ...other } = props;

    return (
        <div
            role="tabpanel"
            hidden={value !== index}
            id={`settings-tabpanel-${index}`}
            aria-labelledby={`settings-tab-${index}`}
            {...other}
        >
            {value === index && (
                <Box sx={{ p: 3 }}>
                    {children}
                </Box>
            )}
        </div>
    );
}

const CompanySetup: React.FC = () => {
    const [tabValue, setTabValue] = useState(0);
    const [settings, setSettings] = useState<CompanySetting[]>([]);
    const [categories, setCategories] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});
    const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' });
    const [settingValues, setSettingValues] = useState<Record<string, string>>({});
    const [testingConnections, setTestingConnections] = useState<Record<string, boolean>>({});
    const [connectionResults, setConnectionResults] = useState<Record<string, {success: boolean, message: string}>>({});

    const categoryIcons: Record<string, React.ReactElement> = {
        'api': <ApiIcon />,
        'network': <NetworkIcon />,
        'notifications': <NotificationsIcon />,
        'general': <BusinessIcon />
    };

    const categoryTabs = [
        { label: 'API Settings', value: 'api' },
        { label: 'Network', value: 'network' },
        { label: 'Notifications', value: 'notifications' },
        { label: 'General', value: 'general' }
    ];

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            setLoading(true);
            
            // First try to load existing settings
            const response = await api.get<CompanySettingsResponse>('/settings');
            
            // If no settings exist, initialize default settings
            if (response.data.settings.length === 0) {
                await api.post('/settings/initialize');
                const newResponse = await api.get<CompanySettingsResponse>('/settings');
                setSettings(newResponse.data.settings);
                setCategories(newResponse.data.categories);
            } else {
                setSettings(response.data.settings);
                setCategories(response.data.categories);
            }

            // Initialize setting values
            const values: Record<string, string> = {};
            response.data.settings.forEach(setting => {
                values[setting.setting_key] = setting.setting_value;
            });
            setSettingValues(values);

        } catch (error) {
            console.error('Error loading settings:', error);
            setSnackbar({ open: true, message: 'Failed to load settings', severity: 'error' });
        } finally {
            setLoading(false);
        }
    };

    const handleSettingChange = (settingKey: string, value: string) => {
        setSettingValues(prev => ({
            ...prev,
            [settingKey]: value
        }));
    };

    const handleSaveSettings = async () => {
        try {
            setSaving(true);
            
            const changedSettings = settings.filter(setting => 
                settingValues[setting.setting_key] !== setting.setting_value
            ).map(setting => ({
                setting_key: setting.setting_key,
                setting_value: settingValues[setting.setting_key]
            }));

            if (changedSettings.length > 0) {
                await api.post('/settings/bulk', { settings: changedSettings });
                setSnackbar({ open: true, message: `Updated ${changedSettings.length} settings successfully`, severity: 'success' });
                await loadSettings(); // Reload to get updated timestamps
            } else {
                setSnackbar({ open: true, message: 'No changes to save', severity: 'success' });
            }

        } catch (error) {
            console.error('Error saving settings:', error);
            setSnackbar({ open: true, message: 'Failed to save settings', severity: 'error' });
        } finally {
            setSaving(false);
        }
    };

    const togglePasswordVisibility = (settingKey: string) => {
        setShowPasswords(prev => ({
            ...prev,
            [settingKey]: !prev[settingKey]
        }));
    };

    const testAPIConnection = async (apiType: string) => {
        setTestingConnections(prev => ({ ...prev, [apiType]: true }));
        
        try {
            const endpoint = apiType === 'splynx' ? '/settings/test-splynx-connection' :
                           apiType === 'mikrotik' ? '/settings/test-mikrotik-connection' :
                           apiType === 'tplink' ? '/settings/test-tplink-connection' :
                           `/settings/test-${apiType}-connection`;
            
            const response = await api.post(endpoint, {
                // Send current form values for testing
                settings: Object.keys(settingValues)
                    .filter(key => key.includes(apiType))
                    .reduce((obj, key) => ({
                        ...obj,
                        [key]: settingValues[key]
                    }), {})
            });
            
            setConnectionResults(prev => ({
                ...prev,
                [apiType]: {
                    success: response.data.success,
                    message: response.data.message || 'Connection successful!'
                }
            }));
            
            setSnackbar({
                open: true,
                message: response.data.success ? `${apiType} connection successful!` : `${apiType} connection failed: ${response.data.message}`,
                severity: response.data.success ? 'success' : 'error'
            });
            
        } catch (error: any) {
            const errorMessage = error?.response?.data?.message || error?.message || 'Connection test failed';
            setConnectionResults(prev => ({
                ...prev,
                [apiType]: {
                    success: false,
                    message: errorMessage
                }
            }));
            
            setSnackbar({
                open: true,
                message: `${apiType} connection test failed: ${errorMessage}`,
                severity: 'error'
            });
        } finally {
            setTestingConnections(prev => ({ ...prev, [apiType]: false }));
        }
    };

    const renderSettingField = (setting: CompanySetting) => {
        const value = settingValues[setting.setting_key] || '';
        const isPassword = setting.setting_type === 'password';
        const showPassword = showPasswords[setting.setting_key];

        if (setting.setting_type === 'boolean') {
            return (
                <FormControlLabel
                    control={
                        <Switch
                            checked={value === 'true'}
                            onChange={(e) => handleSettingChange(setting.setting_key, e.target.checked ? 'true' : 'false')}
                        />
                    }
                    label={setting.description}
                />
            );
        }

        if (setting.setting_type === 'number') {
            return (
                <TextField
                    fullWidth
                    label={setting.description}
                    type="number"
                    value={value}
                    onChange={(e) => handleSettingChange(setting.setting_key, e.target.value)}
                    margin="normal"
                    variant="outlined"
                />
            );
        }

        return (
            <TextField
                fullWidth
                label={setting.description}
                type={isPassword && !showPassword ? 'password' : 'text'}
                value={value}
                onChange={(e) => handleSettingChange(setting.setting_key, e.target.value)}
                margin="normal"
                variant="outlined"
                InputProps={isPassword ? {
                    endAdornment: (
                        <InputAdornment position="end">
                            <IconButton
                                onClick={() => togglePasswordVisibility(setting.setting_key)}
                                edge="end"
                            >
                                {showPassword ? <VisibilityOff /> : <Visibility />}
                            </IconButton>
                        </InputAdornment>
                    )
                } : undefined}
                helperText={
                    setting.setting_key === 'splynx_api_url' ? 'Example: https://your-splynx-server.com/api/2.0' :
                    setting.setting_key === 'tplink_tauc_url' ? 'Example: https://tauc.tplink.com' :
                    setting.setting_key === 'slack_webhook_url' ? 'Slack webhook URL for notifications' :
                    undefined
                }
            />
        );
    };

    const getSettingsByCategory = (category: string) => {
        return settings.filter(setting => setting.category === category);
    };

    const renderCategorySettings = (category: string) => {
        const categorySettings = getSettingsByCategory(category);
        
        if (categorySettings.length === 0) {
            return (
                <Alert severity="info">
                    No settings available for this category.
                </Alert>
            );
        }

        // Group API settings by service type for adding test buttons
        const apiGroups = category === 'api' ? {
            splynx: categorySettings.filter(s => s.setting_key.includes('splynx')),
            mikrotik: categorySettings.filter(s => s.setting_key.includes('mikrotik')),
            tplink: categorySettings.filter(s => s.setting_key.includes('tplink')),
            other: categorySettings.filter(s => !s.setting_key.includes('splynx') && !s.setting_key.includes('mikrotik') && !s.setting_key.includes('tplink'))
        } : null;

        if (category === 'api' && apiGroups) {
            return (
                <Box>
                    {Object.entries(apiGroups).map(([groupName, groupSettings]) => {
                        if (groupSettings.length === 0) return null;
                        
                        return (
                            <Box key={groupName} sx={{ mb: 4 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="h6" sx={{ textTransform: 'capitalize' }}>
                                        {groupName === 'tplink' ? 'TP-Link TUAC' : groupName} API Settings
                                    </Typography>
                                    {groupName !== 'other' && (
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                            {connectionResults[groupName] && (
                                                <Chip 
                                                    size="small"
                                                    label={connectionResults[groupName].success ? 'Connected' : 'Failed'}
                                                    color={connectionResults[groupName].success ? 'success' : 'error'}
                                                />
                                            )}
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                onClick={() => testAPIConnection(groupName)}
                                                disabled={testingConnections[groupName]}
                                                startIcon={testingConnections[groupName] ? <CircularProgress size={16} /> : <ApiIcon />}
                                            >
                                                {testingConnections[groupName] ? 'Testing...' : 'Test Connection'}
                                            </Button>
                                        </Box>
                                    )}
                                </Box>
                                <Grid container spacing={3}>
                                    {groupSettings.map((setting) => (
                                        <Grid item xs={12} md={6} key={setting.setting_key}>
                                            <Card variant="outlined">
                                                <CardContent>
                                                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                                        <Typography variant="subtitle2" sx={{ flex: 1 }}>
                                                            {setting.setting_key}
                                                        </Typography>
                                                        {setting.is_encrypted && (
                                                            <Chip size="small" label="Encrypted" color="secondary" />
                                                        )}
                                                    </Box>
                                                    {renderSettingField(setting)}
                                                </CardContent>
                                            </Card>
                                        </Grid>
                                    ))}
                                </Grid>
                                {connectionResults[groupName] && !connectionResults[groupName].success && (
                                    <Alert severity="error" sx={{ mt: 2 }}>
                                        {connectionResults[groupName].message}
                                    </Alert>
                                )}
                            </Box>
                        );
                    })}
                </Box>
            );
        }

        return (
            <Grid container spacing={3}>
                {categorySettings.map((setting) => (
                    <Grid item xs={12} md={6} key={setting.setting_key}>
                        <Card variant="outlined">
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                    <Typography variant="subtitle2" sx={{ flex: 1 }}>
                                        {setting.setting_key}
                                    </Typography>
                                    {setting.is_encrypted && (
                                        <Chip size="small" label="Encrypted" color="secondary" />
                                    )}
                                </Box>
                                {renderSettingField(setting)}
                            </CardContent>
                        </Card>
                    </Grid>
                ))}
            </Grid>
        );
    };

    if (loading) {
        return (
            <Container maxWidth="lg">
                <Box sx={{ py: 4 }}>
                    <Typography variant="h4" component="h1" gutterBottom>
                        Loading Settings...
                    </Typography>
                </Box>
            </Container>
        );
    }

    return (
        <Container maxWidth="lg">
            <Box sx={{ py: 4 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 4 }}>
                    <SettingsIcon sx={{ mr: 2, fontSize: 40 }} />
                    <Box>
                        <Typography variant="h4" component="h1">
                            Company Settings
                        </Typography>
                        <Typography variant="subtitle1" color="textSecondary">
                            Configure API connections, network settings, and notifications
                        </Typography>
                    </Box>
                </Box>

                <Card>
                    <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                        <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
                            {categoryTabs.map((tab, index) => (
                                <Tab 
                                    key={tab.value}
                                    icon={categoryIcons[tab.value]}
                                    label={tab.label}
                                    iconPosition="start"
                                />
                            ))}
                        </Tabs>
                    </Box>

                    {categoryTabs.map((tab, index) => (
                        <TabPanel key={tab.value} value={tabValue} index={index}>
                            {renderCategorySettings(tab.value)}
                        </TabPanel>
                    ))}

                    <Divider />
                    
                    <Box sx={{ p: 3, display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                        <Button
                            variant="outlined"
                            startIcon={<Refresh />}
                            onClick={loadSettings}
                            disabled={saving}
                        >
                            Reload
                        </Button>
                        <Button
                            variant="contained"
                            startIcon={<Save />}
                            onClick={handleSaveSettings}
                            disabled={saving}
                        >
                            {saving ? 'Saving...' : 'Save Settings'}
                        </Button>
                    </Box>
                </Card>

                <Snackbar
                    open={snackbar.open}
                    autoHideDuration={6000}
                    onClose={() => setSnackbar({ ...snackbar, open: false })}
                >
                    <Alert 
                        onClose={() => setSnackbar({ ...snackbar, open: false })} 
                        severity={snackbar.severity}
                    >
                        {snackbar.message}
                    </Alert>
                </Snackbar>
            </Box>
        </Container>
    );
};

export default CompanySetup;