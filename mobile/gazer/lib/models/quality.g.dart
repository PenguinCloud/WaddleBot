// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'quality.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_QualitySettings _$QualitySettingsFromJson(Map<String, dynamic> json) =>
    _QualitySettings(
      resolution: $enumDecode(_$ResolutionEnumMap, json['resolution']),
      frameRate: $enumDecode(_$FrameRateEnumMap, json['frameRate']),
      videoBitrateKbps: (json['videoBitrateKbps'] as num).toInt(),
      adaptiveBitrate: json['adaptiveBitrate'] as bool,
    );

Map<String, dynamic> _$QualitySettingsToJson(_QualitySettings instance) =>
    <String, dynamic>{
      'resolution': _$ResolutionEnumMap[instance.resolution]!,
      'frameRate': _$FrameRateEnumMap[instance.frameRate]!,
      'videoBitrateKbps': instance.videoBitrateKbps,
      'adaptiveBitrate': instance.adaptiveBitrate,
    };

const _$ResolutionEnumMap = {
  Resolution.p180: 'p180',
  Resolution.p360: 'p360',
  Resolution.p540: 'p540',
  Resolution.p720: 'p720',
  Resolution.p1080: 'p1080',
};

const _$FrameRateEnumMap = {
  FrameRate.fps15: 'fps15',
  FrameRate.fps30: 'fps30',
  FrameRate.fps50: 'fps50',
  FrameRate.fps60: 'fps60',
};
