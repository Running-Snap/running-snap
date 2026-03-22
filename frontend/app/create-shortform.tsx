import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import {
  apiUploadVideo,
  apiCreateShortformJob,
  apiGetShortformJob,
  pollUntilDone,
} from '@/constants/api';

type SelectedVideo = {
  id: string;
  uri: string;
  duration: number | undefined;
  fileName: string;
  mimeType?: string;
};

const STYLES = [
  { key: 'action', label: '스포츠 액션샷' },
  { key: 'instagram', label: '인스타그램' },
  { key: 'tiktok', label: '틱톡' },
  { key: 'humor', label: '밈/유머' },
  { key: 'documentary', label: '다큐' },
] as const;

export default function CreateShortformScreen() {
  const [selectedVideos, setSelectedVideos] = useState<SelectedVideo[]>([]);
  const [style, setStyle] = useState<string>('action');
  const [isLoading, setIsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');

  const handleAddVideo = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('권한 필요', '갤러리 접근 권한이 필요합니다.');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: 'videos',
      allowsEditing: false,
    });

    if (!result.canceled) {
      const asset = result.assets[0];
      const isDuplicate = selectedVideos.some(v => v.uri === asset.uri);
      if (isDuplicate) {
        Alert.alert('알림', '이미 추가된 영상입니다.');
        return;
      }
      setSelectedVideos(prev => [
        ...prev,
        {
          id: asset.assetId ?? asset.uri,
          uri: asset.uri,
          duration: asset.duration ?? undefined,
          fileName: asset.fileName ?? `영상 ${prev.length + 1}`,
          mimeType: asset.mimeType ?? undefined,
        },
      ]);
    }
  };

  const handleRemoveVideo = (id: string) => {
    setSelectedVideos(prev => prev.filter(v => v.id !== id));
  };

  const handleCreateShortform = async () => {
    if (selectedVideos.length < 1) {
      Alert.alert('알림', '영상을 1개 이상 선택해주세요.');
      return;
    }

    setIsLoading(true);
    try {
      // 영상들 순서대로 업로드
      const videoIds: number[] = [];
      for (let i = 0; i < selectedVideos.length; i++) {
        setLoadingText(`영상 업로드 중 (${i + 1}/${selectedVideos.length})...`);
        const { video_id } = await apiUploadVideo(
          selectedVideos[i].uri,
          selectedVideos[i].mimeType,
          selectedVideos[i].fileName,
        );
        videoIds.push(video_id);
      }

      // 숏폼 작업 생성
      setLoadingText('숏폼 만드는 중...');
      const job = await apiCreateShortformJob(videoIds, style, 60);

      // 완료까지 폴링
      const doneJob = await pollUntilDone(() => apiGetShortformJob(job.id));

      router.push({
        pathname: '/shortform-result',
        params: { jobId: String(doneJob.id) },
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '숏폼 생성 실패';
      Alert.alert('오류', msg);
    } finally {
      setIsLoading(false);
      setLoadingText('');
    }
  };

  const formatDuration = (seconds: number | undefined) => {
    if (!seconds) return '길이 미확인';
    const total = seconds > 1000 ? Math.round(seconds / 1000) : Math.round(seconds);
    if (total < 60) return `${total}초`;
    return `${Math.floor(total / 60)}분 ${total % 60}초`;
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#FF3B30" />
        <Text style={styles.loadingTitle}>숏폼을 만들고 있어요</Text>
        <Text style={styles.loadingSubtitle}>{loadingText}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>숏폼 만들기</Text>
      </View>

      <View style={styles.infoCard}>
        <Text style={styles.infoTitle}>✨ 나만의 러닝 숏폼을 만들어보세요</Text>
        <Text style={styles.infoText}>
          여러 영상을 선택하면 AI가 1분 길이의{'\n'}멋진 하이라이트 영상으로 만들어드려요
        </Text>
      </View>

      {/* 스타일 선택 */}
      <View style={styles.styleSection}>
        <Text style={styles.styleLabel}>스타일 선택</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.styleScroll}>
          {STYLES.map(s => (
            <TouchableOpacity
              key={s.key}
              style={[styles.styleChip, style === s.key && styles.styleChipActive]}
              onPress={() => setStyle(s.key)}
            >
              <Text style={[styles.styleChipText, style === s.key && styles.styleChipTextActive]}>
                {s.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      <View style={styles.selectionInfo}>
        <Text style={styles.selectionText}>{selectedVideos.length}개 선택됨</Text>
        {selectedVideos.length > 0 && (
          <TouchableOpacity onPress={() => setSelectedVideos([])}>
            <Text style={styles.clearButton}>전체 삭제</Text>
          </TouchableOpacity>
        )}
      </View>

      <ScrollView style={styles.videoList}>
        <TouchableOpacity style={styles.addButton} onPress={handleAddVideo}>
          <Text style={styles.addButtonIcon}>＋</Text>
          <Text style={styles.addButtonText}>갤러리에서 영상 추가</Text>
        </TouchableOpacity>

        {selectedVideos.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyIcon}>🎥</Text>
            <Text style={styles.emptyText}>아직 선택된 영상이 없어요</Text>
          </View>
        ) : (
          selectedVideos.map((video, index) => (
            <View key={video.id} style={styles.videoCard}>
              <View style={styles.videoThumbnail}>
                <Text style={styles.videoIcon}>🎥</Text>
              </View>
              <View style={styles.videoInfo}>
                <Text style={styles.videoName}>영상 {index + 1}</Text>
                <Text style={styles.videoDetails}>⏱️ {formatDuration(video.duration)}</Text>
              </View>
              <TouchableOpacity style={styles.removeButton} onPress={() => handleRemoveVideo(video.id)}>
                <Text style={styles.removeButtonText}>✕</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.createButton, selectedVideos.length < 1 && styles.createButtonDisabled]}
          onPress={handleCreateShortform}
          disabled={selectedVideos.length < 1}
        >
          <Text style={styles.createButtonText}>
            숏폼 만들기 ({selectedVideos.length}개 선택)
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  header: {
    paddingTop: 60, paddingHorizontal: 20, paddingBottom: 20,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  backButton: { fontSize: 16, color: '#007AFF', marginBottom: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#000' },
  infoCard: {
    backgroundColor: '#fff', margin: 16, padding: 20, borderRadius: 12,
    borderLeftWidth: 4, borderLeftColor: '#FF3B30',
  },
  infoTitle: { fontSize: 16, fontWeight: 'bold', color: '#000', marginBottom: 8 },
  infoText: { fontSize: 14, color: '#666', lineHeight: 20 },
  styleSection: { paddingHorizontal: 16, marginBottom: 8 },
  styleLabel: { fontSize: 14, fontWeight: '600', color: '#666', marginBottom: 8 },
  styleScroll: { flexDirection: 'row' },
  styleChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    backgroundColor: '#f0f0f0', marginRight: 8,
  },
  styleChipActive: { backgroundColor: '#FF3B30' },
  styleChipText: { fontSize: 13, color: '#666' },
  styleChipTextActive: { color: '#fff', fontWeight: 'bold' },
  selectionInfo: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, marginBottom: 8,
  },
  selectionText: { fontSize: 16, fontWeight: 'bold', color: '#000' },
  clearButton: { fontSize: 14, color: '#FF3B30' },
  videoList: { flex: 1, paddingHorizontal: 16 },
  addButton: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12,
    flexDirection: 'row', alignItems: 'center',
    borderWidth: 2, borderColor: '#007AFF', borderStyle: 'dashed',
  },
  addButtonIcon: { fontSize: 24, color: '#007AFF', marginRight: 12, fontWeight: 'bold' },
  addButtonText: { fontSize: 16, color: '#007AFF', fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingVertical: 40 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { fontSize: 16, fontWeight: 'bold', color: '#666' },
  videoCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 12,
    flexDirection: 'row', alignItems: 'center',
  },
  videoThumbnail: {
    width: 60, height: 60, backgroundColor: '#000', borderRadius: 8,
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  videoIcon: { fontSize: 24 },
  videoInfo: { flex: 1 },
  videoName: { fontSize: 16, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  videoDetails: { fontSize: 14, color: '#666' },
  removeButton: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: '#FF3B30',
    alignItems: 'center', justifyContent: 'center',
  },
  removeButtonText: { color: '#fff', fontSize: 14, fontWeight: 'bold' },
  footer: { padding: 16, backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#f0f0f0' },
  createButton: { backgroundColor: '#FF3B30', borderRadius: 12, padding: 16, alignItems: 'center' },
  createButtonDisabled: { backgroundColor: '#ccc' },
  createButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  loadingContainer: { flex: 1, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center', padding: 40 },
  loadingTitle: { fontSize: 22, fontWeight: 'bold', color: '#000', marginTop: 24, marginBottom: 12 },
  loadingSubtitle: { fontSize: 16, color: '#666', textAlign: 'center', lineHeight: 24 },
});
