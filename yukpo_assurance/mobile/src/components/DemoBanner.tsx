import { View, Text, StyleSheet, ViewStyle } from 'react-native'
import { Ionicons } from '@expo/vector-icons'

interface DemoBannerProps {
  message?: string
  style?: ViewStyle
}

export function DemoBanner({ message, style }: DemoBannerProps) {
  return (
    <View
      accessibilityRole="alert"
      style={[styles.container, style]}
    >
      <Ionicons name="warning-outline" size={14} color="#f59e0b" style={styles.icon} />
      <Text style={styles.text}>
        {message ?? 'Données de démonstration — connectez votre source de données pour voir vos indicateurs réels.'}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fffbeb',
    borderColor: '#fde68a',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 6,
  },
  icon: {
    flexShrink: 0,
  },
  text: {
    flex: 1,
    fontSize: 11,
    color: '#92400e',
    lineHeight: 16,
  },
})
