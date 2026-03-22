"""Analyzer 모듈 테스트"""
import asyncio
from src.core.config_loader import ConfigLoader
from src.analyzers import MockFrameAnalyzer, VideoAnalyzer


async def test_analyzer():
    # 설정 로더
    config = ConfigLoader("configs")

    # Mock 분석기 사용 (API 호출 없이 테스트)
    frame_analyzer = MockFrameAnalyzer()
    video_analyzer = VideoAnalyzer(config, frame_analyzer)

    # 테스트할 영상 경로 (실제 파일로 교체 필요)
    test_video = "test_video.mp4"

    try:
        result = await video_analyzer.analyze(
            video_path=test_video,
            target_duration=10,  # 10초 숏폼 목표
            max_concurrent=3
        )

        print(f"\n=== 분석 결과 ===")
        print(f"영상 길이: {result.duration:.1f}초")
        print(f"분석 타입: {result.duration_type.value}")
        print(f"프레임 수: {len(result.frames)}")
        print(f"하이라이트: {result.highlights}")
        print(f"전체 움직임: {result.overall_motion}")
        print(f"요약: {result.summary}")

        if result.story_beats:
            print(f"\n스토리 비트:")
            for section, data in result.story_beats.items():
                print(f"  {section}: motion={data['avg_motion']:.2f}, emotion={data['dominant_emotion']}")

    except Exception as e:
        print(f"에러: {e}")
    finally:
        await frame_analyzer.close()


if __name__ == "__main__":
    asyncio.run(test_analyzer())
