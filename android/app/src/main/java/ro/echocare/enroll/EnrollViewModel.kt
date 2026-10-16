package ro.echocare.enroll

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
import ro.echocare.Caregiver
import ro.echocare.EchoCareApi
import ro.echocare.SeniorPage
import ro.echocare.home.Answer
import ro.echocare.home.EnrollRoute
import ro.echocare.home.Load
import ro.echocare.home.after
import ro.echocare.home.answer

/** „Pacient nou” and its edits: the four steps of seniors §9.2. */
@HiltViewModel
class EnrollViewModel @Inject constructor(private val api: EchoCareApi, handle: SavedStateHandle) :
    ViewModel() {
    /** The senior once saved. Null on a new form until step 1's „Continuă” creates them. */
    var id by mutableStateOf(handle.toRoute<EnrollRoute>().id)
        private set

    /** Opened on a saved senior: from a draft's card or „Editează” (seniors §9.1). */
    val existing = id != null

    /** The form itself: reading a saved senior, ready, or stopped by a refusal (seniors §8.2). */
    var form by mutableStateOf<Load<Unit>>(if (existing) Load.Loading else Load.Ready(Unit))
        private set

    var step by mutableStateOf(Step.Senior)
        private set

    /** The fields of steps 1 and 2, as typed. */
    var values by mutableStateOf(emptyMap<Field, String>())
        private set

    /** What „Continuă” last saved. Back returns to it: what was typed since is dropped. */
    var saved by mutableStateOf(emptyMap<Field, String>())
        private set

    var state by mutableStateOf("draft")
        private set

    var caregivers by mutableStateOf(emptyList<Caregiver>())
        private set

    /** Step 3's row for a new caregiver. */
    var adding by mutableStateOf(emptyMap<Field, String>())
        private set

    /** Step 4's summary, read again each time the step opens. */
    var review by mutableStateOf<Load<SeniorPage>>(Load.Loading)
        private set

    /** A request in flight disables „Continuă”, „Adaugă” and „Trimite la DAS” (SE14). */
    var busy by mutableStateOf(false)
        private set

    /** The server's texts under fields, until the field is typed in again. */
    var errors by mutableStateOf(emptyMap<Field, Int>())
        private set

    var notice by mutableStateOf<Notice?>(null)
        private set

    var submitted by mutableStateOf(false)
        private set

    val draft get() = state == "draft"

    init {
        if (existing) open()
    }

    /** Reads the saved senior into the form, at step 1. Also „Reîncercați”. */
    fun open() {
        val id = id ?: return
        form = Load.Loading
        viewModelScope.launch {
            form = when (val read = answer { api.senior(id) }) {
                is Answer.Ok -> {
                    show(read.value)
                    Load.Ready(Unit)
                }

                is Answer.No -> Load.Failed(read.failure)
            }
        }
    }

    fun type(field: Field, text: String) {
        if (field in REGISTRATION) values += field to text else adding += field to text
        errors -= field
    }

    /** „Continuă”: steps 1 and 2 save first; step 3 sends nothing (seniors §9.2). */
    fun next() {
        when (val save = saveFor(step, id, values)) {
            is Save.Create -> command(Action.Save, { api.createSenior(save.body) }, ::savedAndNext)
            is Save.Update -> command(
                Action.Save,
                { api.updateSenior(save.id, save.body) },
                ::savedAndNext
            )
            Save.None -> go(step.next)
        }
    }

    /** Back: the previous step, or false on step 1, where the form closes. */
    fun back(): Boolean {
        // The answer in flight would land on another step
        if (busy) return true
        if (step == Step.Senior) return false
        values = saved
        adding = emptyMap()
        go(step.previous)
        return true
    }

    fun add() {
        val id = id ?: return
        command(Action.Add, { api.addCaregiver(id, caregiverOf(adding)) }) {
            caregivers = caregivers + it
            adding = emptyMap()
        }
    }

    fun remove(caregiver: Caregiver) {
        val id = id ?: return
        command(Action.Remove, { ensure(api.removeCaregiver(id, caregiver.userId)) }) {
            caregivers = caregivers.filter { it.userId != caregiver.userId }
        }
    }

    /** „Trimite la DAS”: `draft` → `submitted`; the screen then returns to the home. */
    fun submit() {
        val id = id ?: return
        command(Action.Submit, { api.submit(id) }) { submitted = true }
    }

    /** Step 4's summary: GET seniors/{id}, which also refreshes the other steps. */
    fun reread() {
        val id = id ?: return
        review = Load.Loading
        viewModelScope.launch {
            val read = answer { api.senior(id) }
            if (read is Answer.Ok) show(read.value)
            review = review.after(read)
        }
    }

    private fun savedAndNext(page: SeniorPage) {
        show(page)
        go(step.next)
    }

    private fun go(to: Step) {
        step = to
        errors = emptyMap()
        notice = null
        if (to == Step.Review) reread()
    }

    /** The senior as the server holds them: what the fields return to on Back. */
    private fun show(page: SeniorPage) {
        id = page.id
        state = page.state
        caregivers = page.caregivers
        saved = valuesOf(page)
        values = saved
    }

    /** One request at a time (SE14). A refusal becomes what seniors §9.3 shows for it. */
    private fun <T> command(action: Action, call: suspend () -> T, done: (T) -> Unit) {
        if (busy) return
        busy = true
        errors = emptyMap()
        notice = null
        viewModelScope.launch {
            when (val sent = send(call)) {
                is Sent.Ok -> done(sent.value)
                is Sent.No -> refused(thenAfter(action, sent.refusal))
            }
            busy = false
        }
    }

    private fun refused(then: Then) {
        when (then) {
            is Then.Mark -> errors = then.errors
            is Then.Show -> notice = then.notice
            Then.Reread -> go(Step.Review)
            is Then.Stop -> form = Load.Failed(then.failure)
        }
    }
}
