// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'stream_target_settings.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_StreamTargetSettings _$StreamTargetSettingsFromJson(
  Map<String, dynamic> json,
) => _StreamTargetSettings(
  url: json['url'] as String,
  streamKey: json['streamKey'] as String?,
  username: json['username'] as String?,
  password: json['password'] as String?,
);

Map<String, dynamic> _$StreamTargetSettingsToJson(
  _StreamTargetSettings instance,
) => <String, dynamic>{
  'url': instance.url,
  'streamKey': instance.streamKey,
  'username': instance.username,
  'password': instance.password,
};
