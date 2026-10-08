import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Shield, Zap, BarChart3, Users, ArrowRight, CheckCircle2 } from 'lucide-react';

const LandingPage = () => {
  const fadeInUp = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6 }
  };

  const staggerContainer = {
    animate: {
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  return (
    <div className="min-h-screen bg-white text-slate-900 font-sans overflow-x-hidden">
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-white/80 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-200">
              <span className="text-lg font-black text-white italic">C</span>
            </div>
            <span className="text-xl font-black tracking-tighter">ChurnAlert <span className="text-indigo-600">AI</span></span>
          </div>

          <div className="flex items-center gap-4">
            <Link to="/login" className="text-sm font-bold text-slate-900 hover:text-indigo-600 transition-colors">Sign In</Link>
            <Link to="/signup" className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-black hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-100">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 lg:pt-48 lg:pb-32 overflow-hidden">
        {/* Abstract Background Elements */}
        <div className="absolute top-0 right-0 -translate-y-1/4 translate-x-1/4 w-[600px] h-[600px] bg-indigo-50 rounded-full blur-3xl opacity-50"></div>
        <div className="absolute bottom-0 left-0 translate-y-1/4 -translate-x-1/4 w-[600px] h-[600px] bg-purple-50 rounded-full blur-3xl opacity-50"></div>

        <div className="max-w-7xl mx-auto px-6 relative z-10 text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-600 rounded-full text-xs font-black uppercase tracking-widest mb-8 border border-indigo-100"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-600"></span>
            </span>
            Next-Gen Retention Engine
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="text-5xl lg:text-7xl font-black tracking-tight text-slate-900 mb-8 leading-[1.1]"
          >
            Predict churn before <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-purple-600">it even happens.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="max-w-2xl mx-auto text-lg lg:text-xl text-slate-500 font-medium leading-relaxed mb-12"
          >
            Stop losing revenue to customer churn. ChurnAlert AI uses autonomous agents to analyze behavioral signals and automate high-touch retention strategies.
          </motion.p>
          <p className="text-sm text-slate-400 mt-2">Demo project: all companies shown are sample data.</p>

          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Link to="/login" className="w-full sm:w-auto px-10 py-5 bg-slate-900 text-white rounded-2xl font-black hover:bg-slate-800 transition-all shadow-2xl shadow-slate-200 flex items-center justify-center gap-2 group">
              Launch Dashboard <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </motion.div>

          {/* Dashboard Preview */}
          <motion.div
            initial={{ opacity: 0, y: 100 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 0.8 }}
            className="mt-20 relative max-w-5xl mx-auto"
          >
            <div className="absolute inset-0 bg-gradient-to-t from-white via-transparent to-transparent z-10 h-1/4 bottom-0 top-auto"></div>
            <div className="rounded-[40px] border-[8px] border-slate-900/5 shadow-[0_50px_100px_-20px_rgba(0,0,0,0.15)] overflow-hidden bg-white">
              <div className="w-full bg-slate-900 p-6" style={{ minHeight: '400px' }}>
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-3 h-3 rounded-full bg-red-500"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  <div className="ml-4 flex-1 bg-slate-800 rounded-full h-6 flex items-center px-3">
                    <span className="text-slate-500 text-xs">localhost:5173/dashboard</span>
                  </div>
                </div>
                <div className="grid grid-cols-4 gap-3 mb-4">
                  {[['HIGH RISK', '8', '#f43f5e'], ['MEDIUM RISK', '12', '#f59e0b'], ['LOW RISK', '10', '#10b981'], ['MRR', '$6.2k', '#6366f1']].map(([label, val, color], i) => (
                    <div key={i} className="bg-slate-800 rounded-2xl p-3 text-left">
                      <p className="text-slate-500 text-[9px] font-black uppercase tracking-widest mb-1">{label}</p>
                      <p className="text-2xl font-black" style={{ color }}>{val}</p>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-1 bg-slate-800 rounded-2xl p-3 space-y-2">
                    {[['Quantum Dynamics', 'HIGH', '#f43f5e'], ['Orbit Software', 'HIGH', '#f43f5e'], ['Stellar Systems', 'MEDIUM', '#f59e0b'], ['Nova Tech', 'MEDIUM', '#f59e0b'], ['Apex Innovations', 'LOW', '#10b981']].map(([name, tier, color], i) => (
                      <div key={i} className="flex items-center justify-between bg-slate-900 rounded-xl px-3 py-2">
                        <span className="text-white text-xs font-bold">{name}</span>
                        <span className="text-[9px] font-black px-2 py-0.5 rounded-full" style={{ color, backgroundColor: color + '20' }}>{tier}</span>
                      </div>
                    ))}
                  </div>
                  <div className="col-span-2 bg-slate-800 rounded-2xl p-3 text-left">
                    <p className="text-slate-400 text-[9px] font-black uppercase tracking-widest mb-2">AI Risk Analysis</p>
                    <div className="space-y-2">
                      <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-2">
                        <p className="text-red-400 text-[10px] font-bold">• No login in 18 days with renewal in 12 days</p>
                      </div>
                      <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-2">
                        <p className="text-amber-400 text-[10px] font-bold">• Critically low feature adoption (8%)</p>
                      </div>
                      <div className="bg-slate-700 rounded-xl p-2">
                        <p className="text-slate-300 text-[10px]">Recommended: Schedule executive business review. Offer 20% discount on annual upgrade.</p>
                      </div>
                      <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-2 flex items-center justify-between">
                        <p className="text-indigo-400 text-[10px] font-bold">Confidence: HIGH</p>
                        <div className="bg-indigo-600 rounded-lg px-2 py-1">
                          <p className="text-white text-[9px] font-black">Approve & Send</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Floating Badges */}
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              className="absolute -top-10 -right-10 hidden lg:block bg-white p-6 rounded-3xl shadow-2xl border border-slate-100 z-20"
            >
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-emerald-100 rounded-2xl flex items-center justify-center">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600" />
                </div>
                <div className="text-left">
                  <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Churn Prevention</p>
                  <p className="text-2xl font-black text-slate-800">+24.5%</p>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-20 border-y border-slate-50 bg-slate-50/50">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { label: 'Customers', val: '500+' },
              { label: 'Retention Rate', val: '98.2%' },
              { label: 'AI Decisions', val: '2.5M+' },
              { label: 'Revenue Saved', val: '$12M+' },
            ].map((stat, i) => (
              <div key={i} className="text-center">
                <p className="text-4xl lg:text-5xl font-black text-slate-900 mb-2">{stat.val}</p>
                <p className="text-xs font-black uppercase tracking-widest text-slate-400">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-xs font-black uppercase tracking-widest text-indigo-600 mb-4">Enterprise Grade</h2>
            <h3 className="text-4xl lg:text-5xl font-black tracking-tight text-slate-900 mb-6">Everything you need to <br />scale customer success.</h3>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                icon: <Zap className="w-6 h-6 text-indigo-600" />,
                title: "Real-time Detection",
                desc: "Identify usage drops and behavioral shifts as they happen, not weeks later."
              },
              {
                icon: <Shield className="w-6 h-6 text-purple-600" />,
                title: "Sentiment Analysis",
                desc: "Automatically parse support tickets and feedback for emotional intent and risk."
              },
              {
                icon: <BarChart3 className="w-6 h-6 text-pink-600" />,
                title: "Predictive Scoring",
                desc: "Proprietary AI models assign dynamic risk scores to every single account."
              },
              {
                icon: <Users className="w-6 h-6 text-blue-600" />,
                title: "Automated Outreach",
                desc: "Generate personalized, empathetic outreach drafts for your CSM team instantly."
              },
              {
                icon: <CheckCircle2 className="w-6 h-6 text-emerald-600" />,
                title: "Outcome Tracking",
                desc: "Measure the direct impact of AI interventions on your bottom line revenue."
              },
              {
                icon: <Zap className="w-6 h-6 text-amber-600" />,
                title: "CRM Integration",
                desc: "Syncs perfectly with Salesforce, Hubspot, and your existing data stack."
              },
            ].map((feature, i) => (
              <motion.div
                key={i}
                whileHover={{ y: -10 }}
                className="p-10 bg-white border border-slate-100 rounded-[32px] shadow-sm hover:shadow-xl hover:shadow-indigo-500/5 transition-all"
              >
                <div className="w-14 h-14 bg-slate-50 rounded-2xl flex items-center justify-center mb-8">
                  {feature.icon}
                </div>
                <h4 className="text-xl font-black text-slate-900 mb-4">{feature.title}</h4>
                <p className="text-slate-500 font-medium leading-relaxed">{feature.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 lg:py-32 px-6">
        <div className="max-w-5xl mx-auto bg-slate-900 rounded-[48px] p-12 lg:p-24 relative overflow-hidden text-center">
          <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/20 blur-[100px] rounded-full translate-x-1/2 -translate-y-1/2"></div>
          <div className="absolute bottom-0 left-0 w-96 h-96 bg-purple-500/20 blur-[100px] rounded-full -translate-x-1/2 translate-y-1/2"></div>

          <div className="relative z-10">
            <h3 className="text-4xl lg:text-6xl font-black text-white tracking-tight mb-8">Ready to transform your <br />retention strategy?</h3>
            <p className="text-slate-400 text-lg mb-12 max-w-xl mx-auto">Try the live demo. All companies shown are sample data for this capstone project.</p>
            <Link to="/signup" className="inline-flex px-12 py-6 bg-white text-slate-900 rounded-2xl font-black hover:bg-slate-50 transition-all shadow-xl shadow-white/10">
              Launch Demo
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-slate-100">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-200">
              <span className="text-lg font-black text-white italic">C</span>
            </div>
            <span className="text-xl font-black tracking-tighter text-slate-900">ChurnAlert <span className="text-indigo-600">AI</span></span>
          </div>

          <p className="text-slate-400 text-sm font-medium">© 2026 ChurnAlert AI, a capstone project.</p>

          <div className="flex gap-6 text-sm font-bold text-slate-500">
            <span>ChurnAlert AI © 2026</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
