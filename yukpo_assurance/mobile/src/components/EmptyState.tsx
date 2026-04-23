import { ReactNode } from 'react'
import { View, Text, StyleSheet, ViewStyle } from 'react-native'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description?: string
  action?: ReactNode
  style?: ViewStyle
}

export function EmptyState({ icon, title, description, action, style }: EmptyStateProps) {
  return (
    <View accessibilityRole="text" style={[styles.container, style]}>
      <View style={styles.icon}>{icon}</View>
      <Text style={styles.title}>{title}</Text>
      {description ? <Text style={styles.description}>{description}</Text> : null}
      {action ? <View style={styles.action}>{action}</View> : null}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 48,
    paddingHorizontal: 24,
  },
  icon: {
    marginBottom: 12,
    opacity: 0.4,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    textAlign: 'center',
  },
  description: {
    fontSize: 12,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 4,
    maxWidth: 320,
  },
  action: {
    marginTop: 16,
  },
})
