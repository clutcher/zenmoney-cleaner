export const meta = {
  name: 'run-jobs',
  description: 'zenmoney-cleaner: run the agent jobs of 1 stage that the code prepared, each job as its steps in order and the jobs side by side',
  whenToUse: 'Started by the categorize skill of zenmoney-cleaner with the path of a jobs.workflow.js file',
  phases: [{ title: 'Jobs', detail: 'one chain of agent steps per job; each step reads its task file and writes its answer file' }],
}

const PLUGIN = 'zenmoney-cleaner'
const ATTEMPTS = 2

const STEP_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['written', 'failed'] },
    count: { type: 'integer' },
    problem: { type: 'string' },
  },
  required: ['status'],
}

const loadJobs = async jobsScriptPath => {
  if (!jobsScriptPath) {
    throw new Error('args.jobs must name the jobs.workflow.js file of the stage')
  }
  return await workflow({ scriptPath: String(jobsScriptPath).replace(/\\/g, '/') })
}

const runStep = async step => {
  const prompt = `Task file: ${step.task}\nAnswer file: ${step.answer}`
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    const result = await agent(prompt, {
      label: attempt === 1 ? step.label : `${step.label} (again)`,
      phase: 'Jobs',
      agentType: `${PLUGIN}:${step.agent}`,
      schema: STEP_RESULT_SCHEMA,
    })
    if (result && result.status === 'written') {
      return { label: step.label, status: 'written', count: result.count ?? null }
    }
    if (attempt === ATTEMPTS) {
      return { label: step.label, status: 'failed', problem: result ? result.problem ?? '' : 'the agent stopped' }
    }
  }
}

const runJob = async job => {
  const stepResults = []
  for (const step of job) {
    const stepResult = await runStep(step)
    stepResults.push(stepResult)
    if (stepResult.status !== 'written') {
      break
    }
  }
  return stepResults
}

phase('Jobs')
const prepared = await loadJobs(args && args.jobs)
log(`${prepared.stage}: ${prepared.jobs.length} jobs`)
const jobResults = await parallel(prepared.jobs.map(job => () => runJob(job)))
const stepResults = jobResults.filter(Boolean).flat()
const failed = stepResults.filter(stepResult => stepResult.status !== 'written')
if (failed.length) {
  log(`${failed.length} steps failed: ${failed.map(stepResult => stepResult.label).join(', ')}`)
}
return { stage: prepared.stage, written: stepResults.length - failed.length, failed }
