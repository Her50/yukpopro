import { useEffect } from 'react'
import { useRouter } from 'expo-router'
import { View, ActivityIndicator } from 'react-native'
import { useAuth } from '../src/context/AuthContext'

export default function Index() {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading) {
      if (isAuthenticated) {
        router.replace('/(tabs)/dashboard')
      } else {
        router.replace('/login')
      }
    }
  }, [isAuthenticated, isLoading])

  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#1e40af' }}>
      <ActivityIndicator size="large" color="#ffffff" />
    </View>
  )
}
