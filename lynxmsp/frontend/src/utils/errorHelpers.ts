// Error handling utilities
export const getErrorMessage = (error: any): string => {
  if (error?.response?.data?.message) {
    return error.response.data.message;
  }
  if (error?.message) {
    return error.message;
  }
  return 'An unknown error occurred';
};

export const handleApiError = (error: any, defaultMessage: string = 'An error occurred'): string => {
  console.error('API Error:', error);
  return getErrorMessage(error) || defaultMessage;
};