package ro.echocare.das

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.toRoute
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch
import ro.echocare.EchoCareApi
import ro.echocare.Resolution
import ro.echocare.enroll.Sent
import ro.echocare.enroll.send
import ro.echocare.home.ResolveRoute

/**
 * „Rezolvare caz”: POST /incidents/{id}/resolve with an outcome and a note (UC-11 step 4). It
 * reads nothing, so no background read can wipe what is being typed.
 */
@HiltViewModel
class ResolveViewModel @Inject constructor(private val api: EchoCareApi, saved: SavedStateHandle) :
    ViewModel() {
    private val id = saved.toRoute<ResolveRoute>().id

    var outcome by mutableStateOf<String?>(null)
    var note by mutableStateOf("")
    var sending by mutableStateOf(false)
        private set

    /** Why the last Trimite was refused; what was typed stays. */
    var notice by mutableStateOf<Notice?>(null)
        private set

    /** Not `send`: a member taking `() -> Unit` would capture the call to [send] below. */
    fun submit(onDone: () -> Unit) {
        val picked = outcome
        if (picked == null || !canSend(picked, note) || sending) return
        sending = true
        viewModelScope.launch {
            when (val sent = send { api.resolve(id, Resolution(picked, note.trim())) }) {
                is Sent.Ok -> onDone()
                is Sent.No -> notice = noticeAfter(sent.refusal, Act.Resolve)
            }
            sending = false
        }
    }
}
