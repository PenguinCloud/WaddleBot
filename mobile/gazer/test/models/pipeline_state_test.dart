import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/pipeline_state.dart';

void main() {
  group('GazerErrorCode', () {
    test('exposes all thirteen native error codes', () {
      expect(GazerErrorCode.values, hasLength(13));
      expect(
        GazerErrorCode.values,
        contains(GazerErrorCode.usbPermissionDenied),
      );
      expect(GazerErrorCode.values, contains(GazerErrorCode.uvcNoUsableFormat));
      expect(GazerErrorCode.values, contains(GazerErrorCode.uvcOpenFailed));
      expect(GazerErrorCode.values, contains(GazerErrorCode.cameraUnavailable));
      expect(GazerErrorCode.values, contains(GazerErrorCode.cameraInUse));
      expect(GazerErrorCode.values, contains(GazerErrorCode.encoderFailed));
      expect(GazerErrorCode.values, contains(GazerErrorCode.audioSourceFailed));
      expect(GazerErrorCode.values, contains(GazerErrorCode.rtmpAuthFailed));
      expect(GazerErrorCode.values, contains(GazerErrorCode.rtmpConnectFailed));
      expect(GazerErrorCode.values, contains(GazerErrorCode.rtmpDisconnected));
      expect(GazerErrorCode.values, contains(GazerErrorCode.usbDetached));
      expect(
        GazerErrorCode.values,
        contains(GazerErrorCode.serviceStartDenied),
      );
      expect(GazerErrorCode.values, contains(GazerErrorCode.unknown));
    });
  });

  group('GazerError equality', () {
    test('same code and detail are equal', () {
      const a = GazerError(
        code: GazerErrorCode.rtmpConnectFailed,
        detail: 'timeout',
      );
      const b = GazerError(
        code: GazerErrorCode.rtmpConnectFailed,
        detail: 'timeout',
      );
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing detail breaks equality', () {
      const a = GazerError(
        code: GazerErrorCode.rtmpConnectFailed,
        detail: 'timeout',
      );
      const b = GazerError(
        code: GazerErrorCode.rtmpConnectFailed,
        detail: 'refused',
      );
      expect(a == b, isFalse);
    });
  });

  group('PipelineState subclasses', () {
    test('each stateless subclass equals another instance of itself', () {
      expect(const IdleState(), const IdleState());
      expect(const PreparingState(), const PreparingState());
      expect(const ReadyState(), const ReadyState());
      expect(const ConnectingState(), const ConnectingState());
      expect(const StreamingState(), const StreamingState());
      expect(const StoppingState(), const StoppingState());
    });

    test('IdleState is never equal to PreparingState', () {
      expect(const IdleState() == const PreparingState(), isFalse);
    });

    test('ReconnectingState compares by attempt and nextIn', () {
      const a = ReconnectingState(2, Duration(seconds: 4));
      const b = ReconnectingState(2, Duration(seconds: 4));
      const c = ReconnectingState(3, Duration(seconds: 4));
      expect(a, b);
      expect(a.hashCode, b.hashCode);
      expect(a == c, isFalse);
    });

    test('ErrorState compares by wrapped GazerError', () {
      const a = ErrorState(GazerError(code: GazerErrorCode.rtmpAuthFailed));
      const b = ErrorState(GazerError(code: GazerErrorCode.rtmpAuthFailed));
      const c = ErrorState(GazerError(code: GazerErrorCode.unknown));
      expect(a, b);
      expect(a == c, isFalse);
    });

    test('a switch expression over PipelineState is exhaustive', () {
      String describe(PipelineState s) => switch (s) {
        IdleState() => 'idle',
        PreparingState() => 'preparing',
        ReadyState() => 'ready',
        ConnectingState() => 'connecting',
        StreamingState() => 'streaming',
        ReconnectingState() => 'reconnecting',
        StoppingState() => 'stopping',
        ErrorState() => 'error',
      };
      expect(describe(const IdleState()), 'idle');
      expect(
        describe(const ErrorState(GazerError(code: GazerErrorCode.unknown))),
        'error',
      );
    });

    test('stateless states have a class-named toString', () {
      expect(const IdleState().toString(), 'IdleState()');
      expect(const PreparingState().toString(), 'PreparingState()');
      expect(const ReadyState().toString(), 'ReadyState()');
      expect(const ConnectingState().toString(), 'ConnectingState()');
      expect(const StreamingState().toString(), 'StreamingState()');
      expect(const StoppingState().toString(), 'StoppingState()');
    });

    test('stateless states hash to their runtime Type object hashCode', () {
      expect(const IdleState().hashCode, (IdleState).hashCode);
      expect(const PreparingState().hashCode, (PreparingState).hashCode);
      expect(const ReadyState().hashCode, (ReadyState).hashCode);
      expect(const ConnectingState().hashCode, (ConnectingState).hashCode);
      expect(const StreamingState().hashCode, (StreamingState).hashCode);
      expect(const StoppingState().hashCode, (StoppingState).hashCode);
    });

    test('ReconnectingState toString includes attempt and nextIn', () {
      const state = ReconnectingState(2, Duration(seconds: 4));
      expect(
        state.toString(),
        'ReconnectingState(attempt: 2, nextIn: ${state.nextIn})',
      );
    });

    test('ErrorState toString and hashCode delegate to the wrapped error', () {
      const error = GazerError(code: GazerErrorCode.unknown);
      const state = ErrorState(error);
      expect(state.hashCode, error.hashCode);
      expect(state.toString(), 'ErrorState(error: $error)');
    });

    test('GazerError toString includes code and detail', () {
      const error = GazerError(
        code: GazerErrorCode.rtmpConnectFailed,
        detail: 'timeout',
      );
      expect(
        error.toString(),
        'GazerError(code: GazerErrorCode.rtmpConnectFailed, detail: timeout)',
      );
    });
  });
}
